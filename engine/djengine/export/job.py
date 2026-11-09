"""dj_export job: send the library (or a selection) to Rekordbox, VirtualDJ or Serato."""
import asyncio
from pathlib import Path

from ..errors import UserError
from .model import collect
from .rekordbox import rekordbox_xml, write_rekordbox

TITLES = {"rekordbox": "Rekordbox", "virtualdj": "VirtualDJ", "serato": "Serato"}


def default_rekordbox_out(svc) -> Path:
    return Path(svc.settings.music_dir) / "OneForAll rekordbox.xml"


def make_dj_export_runner(svc, target: str, track_ids: list[int] | None, out: str | None):
    async def run(ctx) -> dict:
        try:
            result = await _export(ctx)
        except UserError:
            svc.library.add_history(None, TITLES[target], "", "export", "failed")
            raise
        svc.library.add_history(None, TITLES[target], "", "export", "done")
        return result

    async def _export(ctx) -> dict:
        ctx.report("collecting", 0)
        tracks, skipped = await asyncio.to_thread(collect, svc, track_ids)
        ctx.check_cancelled()
        ctx.report("writing", 10)
        file = None
        exported = 0
        if target == "rekordbox":
            ids = {t.id for t in tracks}
            playlists = [(name, [i for i in svc.library.playlist_track_ids(pid) if i in ids])
                         for pid, name in svc.library.list_playlists()]
            dest = Path(out) if out else default_rekordbox_out(svc)
            xml = await asyncio.to_thread(rekordbox_xml, tracks, [p for p in playlists if p[1]])
            await asyncio.to_thread(write_rekordbox, dest, xml)
            exported, file = len(tracks), str(dest)
        elif target == "virtualdj":
            from .virtualdj import write_virtualdj

            written, sk = await asyncio.to_thread(write_virtualdj, tracks)
            skipped += sk
            exported = len(tracks) - len(sk)
            file = str(written[0]) if written else None
        else:
            from .serato import export_serato

            for i, t in enumerate(tracks):
                ctx.check_cancelled()
                try:
                    await asyncio.to_thread(export_serato, svc, t)
                    exported += 1
                except UserError as e:
                    skipped.append({"title": t.title, "reason": e.message})
                ctx.report("writing", 10 + 90 * (i + 1) / max(1, len(tracks)))
        return {"exported": exported, "skipped": skipped, "file": file}

    return run
