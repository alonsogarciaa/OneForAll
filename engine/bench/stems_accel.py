"""Export the htdemucs_6s core to ONNX, run it with DirectML and gate it against PyTorch on the CPU.

The complex STFT / mask / iSTFT stay in PyTorch on the CPU (DirectML has no complex dtype); everything in
between (encoders, cross-transformer, decoders) goes to ONNX. Gate (spec §6): every stem >= 40 dB SNR vs
CPU on 5 real tracks and >= 1.5x faster. Writes docs/bench/2026-11-fase3a-accel.md and
bench/data/onnx/accel_validated.json.

Run in an env with onnxruntime-directml (it conflicts with the CPU onnxruntime wheel):
    uv run --no-project --python 3.12 --with demucs --with onnx --with onnxruntime-directml --with soundfile \
        python -m bench.stems_accel <audio files...>
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from torch import nn

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "onnx"
REPORT = HERE.parents[1] / "docs" / "bench" / "2026-11-fase3a-accel.md"
SECONDS = 30


class Core(nn.Module):
    """HTDemucs.forward minus the complex parts: (mag, mix) -> (spec branch x, time branch xt)."""

    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, mag, mix):
        m = self.m
        x = mag
        B, C, Fq, T = x.shape
        mean = x.mean(dim=(1, 2, 3), keepdim=True)
        std = x.std(dim=(1, 2, 3), keepdim=True)
        x = (x - mean) / (1e-5 + std)
        xt = mix
        meant = xt.mean(dim=(1, 2), keepdim=True)
        stdt = xt.std(dim=(1, 2), keepdim=True)
        xt = (xt - meant) / (1e-5 + stdt)
        saved, saved_t, lengths, lengths_t = [], [], [], []
        for idx, encode in enumerate(m.encoder):
            lengths.append(x.shape[-1])
            inject = None
            if idx < len(m.tencoder):
                lengths_t.append(xt.shape[-1])
                tenc = m.tencoder[idx]
                xt = tenc(xt)
                if not tenc.empty:
                    saved_t.append(xt)
                else:
                    inject = xt
            x = encode(x, inject)
            if idx == 0 and m.freq_emb is not None:
                frs = torch.arange(x.shape[-2], device=x.device)
                emb = m.freq_emb(frs).t()[None, :, :, None].expand_as(x)
                x = x + m.freq_emb_scale * emb
            saved.append(x)
        if m.crosstransformer:
            if m.bottom_channels:
                b, c, f, t = x.shape
                x = x.reshape(b, c, f * t)
                x = m.channel_upsampler(x)
                x = x.reshape(b, -1, f, t)
                xt = m.channel_upsampler_t(xt)
            x, xt = m.crosstransformer(x, xt)
            if m.bottom_channels:
                b, c, f, t = x.shape
                x = x.reshape(b, c, f * t)
                x = m.channel_downsampler(x)
                x = x.reshape(b, -1, f, t)
                xt = m.channel_downsampler_t(xt)
        for idx, decode in enumerate(m.decoder):
            skip = saved.pop(-1)
            x, pre = decode(x, skip, lengths.pop(-1))
            offset = m.depth - len(m.tdecoder)
            if idx >= offset:
                tdec = m.tdecoder[idx - offset]
                length_t = lengths_t.pop(-1)
                if tdec.empty:
                    pre = pre[:, :, 0]
                    xt, _ = tdec(pre, None, length_t)
                else:
                    skip = saved_t.pop(-1)
                    xt, _ = tdec(xt, skip, length_t)
        S = len(m.sources)
        x = x.view(B, S, -1, Fq, T)
        x = x * std[:, None] + mean[:, None]
        xt = xt.view(B, S, -1, mix.shape[-1])
        xt = xt * stdt[:, None] + meant[:, None]
        return x, xt


def patch_with_session(model, session):
    """Replace model.forward with: CPU complex STFT -> ONNX core -> CPU mask/iSTFT."""
    training_length = int(model.segment * model.samplerate)

    def forward(mix):
        length_pre_pad = None
        if mix.shape[-1] < training_length:
            length_pre_pad = mix.shape[-1]
            mix = torch.nn.functional.pad(mix, (0, training_length - length_pre_pad))
        z = model._spec(mix)
        mag = model._magnitude(z)
        x, xt = session.run(None, {"mag": mag.numpy(), "mix": mix.numpy()})
        x = model._ispec(model._mask(z, torch.from_numpy(x)), training_length)
        out = torch.from_numpy(xt) + x
        return out[..., :length_pre_pad] if length_pre_pad else out

    model.forward = forward


def export(model) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "htdemucs_6s.onnx"
    L = int(model.segment * model.samplerate)
    mix = torch.zeros(1, 2, L)
    mag = model._magnitude(model._spec(mix))
    torch.onnx.export(Core(model).eval(), (mag, mix), str(path), input_names=["mag", "mix"],
                      output_names=["x", "xt"], opset_version=17, dynamo=False)
    return path


def separate(model, audio):
    from demucs.apply import apply_model

    t = time.perf_counter()
    with torch.no_grad():
        out = apply_model(model, torch.from_numpy(audio)[None], split=True, overlap=0.25, shifts=0, progress=False)[0]
    return out.numpy(), time.perf_counter() - t


def snr(ref, est):
    return float(10 * np.log10((np.sum(ref ** 2) + 1e-9) / (np.sum((est - ref) ** 2) + 1e-9)))


def main(files: list[str]) -> None:
    import onnxruntime as ort
    from demucs.pretrained import get_model

    bag = get_model("htdemucs_6s")
    model = bag.models[0] if hasattr(bag, "models") else bag
    model.eval()
    lines = [f"# Aceleración de stems: ONNX + DirectML ({date.today().isoformat()})", ""]
    try:
        onnx_path = export(model)
    except Exception as e:  # export not possible: stay on CPU
        result = {"passed": False, "reason": f"export failed: {type(e).__name__}: {e}"[:500]}
        (OUT / "accel_validated.json").write_text(json.dumps(result, indent=1))
        REPORT.write_text("\n".join(lines + [f"Exportación a ONNX fallida: `{result['reason']}`.", "", "Resultado: **CPU**."]) + "\n", encoding="utf-8")
        print(result)
        return
    providers = ort.get_available_providers()
    use = ["DmlExecutionProvider", "CPUExecutionProvider"] if "DmlExecutionProvider" in providers else ["CPUExecutionProvider"]
    sess = ort.InferenceSession(str(onnx_path), providers=use)
    rows, ok = [], True
    for f in files:
        y, sr = sf.read(f, dtype="float32", always_2d=True)
        audio = np.ascontiguousarray(y[: SECONDS * sr].T)
        ref, t_cpu = separate(bag, audio)
        orig = model.forward
        patch_with_session(model, sess)
        est, t_acc = separate(bag, audio)
        model.forward = orig
        snrs = {s: snr(ref[i], est[i]) for i, s in enumerate(model.sources)}
        speed = t_cpu / t_acc
        ok &= min(snrs.values()) >= 40 and speed >= 1.5
        rows.append((Path(f).name, snrs, t_cpu, t_acc, speed))
        print(Path(f).name, {k: round(v, 1) for k, v in snrs.items()}, round(speed, 2), flush=True)
    lines += [f"Proveedor ONNX: {use[0]}. {len(rows)} pistas reales, {SECONDS} s cada una.", "",
              "| Pista | " + " | ".join(model.sources) + " | CPU s | ONNX s | × |",
              "|---|" + "---|" * len(model.sources) + "---|---|---|"]
    for name, snrs, tc, ta, sp in rows:
        lines.append(f"| {name[:40]} | " + " | ".join(f"{snrs[s]:.1f} dB" for s in model.sources) + f" | {tc:.1f} | {ta:.1f} | {sp:.2f} |")
    lines += ["", "Umbral (spec §6): cada stem ≥ 40 dB frente a la CPU y ≥ 1,5× más rápido.",
              f"Resultado: **{'DirectML activado' if ok else 'CPU (no supera el umbral)'}**."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "accel_validated.json").write_text(json.dumps({"passed": bool(ok), "provider": use[0]}, indent=1))
    print("passed", ok)


if __name__ == "__main__":
    main(sys.argv[1:])
