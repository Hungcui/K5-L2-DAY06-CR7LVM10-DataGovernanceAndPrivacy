"""YOUR PoC PIPELINE — this is the file your group owns.

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   your algorithm / model (the research part)
    03 rank      prioritise for a fixed review budget B
    04 review    human-in-the-loop: queue -> reviewer decisions -> overrides + audit log
    05 decide    GO / HOLD / REWORK (or track equivalent) with reason_code + owner, write outputs

Required output: out/<pred_file> with the columns listed for your track in
docs/tracks/TXX.md (also in src/metrics/tracks.py::TRACKS). Then evaluate with
    python -m src.evaluate --track tXX --pred out/<pred_file>

Rules: never read fixtures/*/gt/ here (the GT guard will stop you); seed everything via ctx.rng;
no network calls; fail loudly on missing models instead of downloading.
See src/examples/random_baseline.py for a minimal end-to-end wiring example.
"""
from __future__ import annotations

import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    data = {"manifest": pd.read_csv(manifest) if manifest.exists() else None}
    images_csv = ctx.input_dir / "images.csv"
    if images_csv.exists():
        data["images"] = pd.read_csv(images_csv)
    return data


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    spec = get_track(ctx.track)
    if ctx.track == "t02":
        from . import t02_qc
        if "images" not in data or data["images"] is None:
            raise ValueError("t02 requires images.csv in input directory")
        ranked = t02_qc.run_poc(data["images"], ctx.input_dir, cfg=ctx.config.get("params", {}))
        return t02_qc.to_output(ranked)
    raise NotImplementedError(
        f"Implement process() for {spec.track} ({spec.title}). It must produce a DataFrame with at least "
        f"{spec.pred_columns} (saved as out/{spec.pred_file}). See docs/tracks/{spec.track.upper()}.md"
    )


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Default: top-B by `score`. Adapt id/score/reason columns to your track."""
    budget = int(ctx.param("budget", 20))
    if "score" not in scored.columns:
        raise ValueError("rank(): process() output needs a numeric `score` column (higher = review first), "
                         "or adapt rank() to your track")
    evidence = "path" if "path" in scored.columns else None
    q = make_review_queue(scored, id_col=scored.columns[0], score_col="score", budget=budget,
                          reason_col="reason" if "reason" in scored.columns else None,
                          evidence_col=evidence)
    write_review_queue(q, ctx.out("review_queue.csv"))
    if evidence:
        from .common.contact_sheet import render_contact_sheet
        render_contact_sheet(q, ctx.out("contact_sheet.html"), image_root=ctx.input_dir,
                             title=f"T02 Raw QC Review Queue (top-{budget})")
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """If a reviewed queue exists (out/review_queue_reviewed.csv), apply it. Otherwise pass through."""
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        out = scored.copy()
        for _, row in reviewed.iterrows():
            item_id = str(row["item_id"])
            dec = row.get("reviewer_decision")
            if dec in ("approve", "reject", "edit"):
                ctx.audit.log(actor=str(row.get("reviewer", "reviewer")), action="reviewer_override",
                              item_id=item_id, after={"decision": dec, "note": str(row.get("review_note", ""))})
                idx = out[out[out.columns[0]] == item_id].index
                if len(idx):
                    if dec == "approve":
                        out.loc[idx, "score"] = 0.0
                        if "pred_action" in out.columns:
                            out.loc[idx, "pred_action"] = "KEEP"
                    elif dec == "reject":
                        out.loc[idx, "score"] = max(out.loc[idx, "score"].max(), 5.0)
                        if "pred_action" in out.columns:
                            out.loc[idx, "pred_action"] = "RECAPTURE"
        return out
    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    if ctx.track == "t02":
        from . import t02_qc
        status, reason_code = t02_qc.batch_decision(final, split="eval", max_recapture_rate=0.4)
        recapture_count = int((final.get("pred_action", "") == "RECAPTURE").sum()) if "pred_action" in final.columns else 0
        return Decision(
            status=status,
            reason_code=reason_code,
            reason=f"T02 QC batch decision: {recapture_count}/{len(final)} items flagged for recapture",
            owner=ctx.config.get("owner", "Team Lead (CR7LVM10)"),
            scope=ctx.track,
            evidence=[str(ctx.out("ranked_review.csv")), str(ctx.out("review_queue.csv"))]
        )
    return Decision(status="HOLD", reason_code="POLICY_NOT_IMPLEMENTED", reason="Decision policy not implemented yet",
                    owner=ctx.config.get("owner", "TODO-owner"), scope=ctx.track)


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    final[spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
