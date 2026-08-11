from __future__ import annotations

import json

from .base import Detection, SessionTrace, register


@register
class TodoStagnation:
    name = "todo_stagnation"

    def run(self, session: SessionTrace) -> list[Detection]:
        if not session.todo_snapshots:
            return []
        last = json.loads(session.todo_snapshots[-1]["items_json"])
        if len(last) <= 1:
            return []
        completed = sum(1 for t in last if t.get("status") == "completed")
        out = []
        if completed == 0:
            out.append(
                Detection(
                    kind=self.name,
                    level="warn",
                    message=f"К концу сессии не закрыт ни один из {len(last)} пунктов плана",
                    evidence={"todo_count": len(last)},
                )
            )
        missing_ids = [t for t in last if not t.get("id")]
        if missing_ids:
            out.append(
                Detection(
                    kind=self.name,
                    level="info",
                    message="У пунктов плана нет стабильного id — статусы адресуются только по позиции в снимке, не полагайтесь на id между снимками",
                    evidence={"count": len(missing_ids)},
                )
            )
        return out
