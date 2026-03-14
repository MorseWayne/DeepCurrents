from __future__ import annotations

from collections.abc import Mapping

from loguru import logger

from .report_models import DailyReport


# ── Report Quality Evaluator ──


class ReportEvaluator:
    def __init__(
        self,
        *,
        min_executive_summary_len: int = 50,
        min_economic_analysis_len: int = 80,
        min_investment_trends: int = 1,
        min_asset_breakdowns: int = 1,
    ):
        self._min_exec_len: int = min_executive_summary_len
        self._min_econ_len: int = min_economic_analysis_len
        self._min_trends: int = min_investment_trends
        self._min_breakdowns: int = min_asset_breakdowns

    def evaluate(self, report: DailyReport) -> Mapping[str, object]:
        scores: dict[str, float] = {}
        issues: list[str] = []

        # Executive summary quality
        exec_text = (report.executiveSummary or "").strip()
        if len(exec_text) >= self._min_exec_len:
            scores["executive_summary"] = min(100.0, len(exec_text) / 3.0)
        else:
            scores["executive_summary"] = max(
                0.0, len(exec_text) / self._min_exec_len * 40
            )
            issues.append(f"executiveSummary too short ({len(exec_text)} chars)")

        # Economic analysis quality
        econ_text = (report.economicAnalysis or "").strip()
        if len(econ_text) >= self._min_econ_len:
            scores["economic_analysis"] = min(100.0, len(econ_text) / 4.0)
        else:
            scores["economic_analysis"] = max(
                0.0, len(econ_text) / self._min_econ_len * 40
            )
            issues.append(f"economicAnalysis too short ({len(econ_text)} chars)")

        # Macro transmission chain
        chain = report.macroTransmissionChain
        if chain:
            has_headline = bool(chain.headline.strip())
            has_steps = len(chain.steps) >= 2
            scores["macro_chain"] = 80.0 if (has_headline and has_steps) else 40.0
        else:
            scores["macro_chain"] = 0.0
            issues.append("macroTransmissionChain missing or empty")

        # Investment trends
        trends = report.investmentTrends or []
        if len(trends) >= self._min_trends:
            unique_assets = {
                trend.assetClass.strip()
                for trend in trends
                if trend.assetClass and trend.assetClass.strip()
            }
            scores["investment_trends"] = min(100.0, len(unique_assets) * 25.0)
        else:
            scores["investment_trends"] = 0.0
            issues.append(
                f"investmentTrends count ({len(trends)}) below minimum ({self._min_trends})"
            )

        # Asset transmission breakdowns
        breakdowns = report.assetTransmissionBreakdowns or []
        if len(breakdowns) >= self._min_breakdowns:
            informative = sum(
                1
                for b in breakdowns
                if b.coreView.strip() and b.transmissionPath.strip()
            )
            scores["asset_breakdowns"] = min(100.0, informative * 25.0)
        else:
            scores["asset_breakdowns"] = 0.0
            issues.append(
                f"assetTransmissionBreakdowns count ({len(breakdowns)}) below minimum"
            )

        # Overall composite score
        weights = {
            "executive_summary": 0.20,
            "economic_analysis": 0.15,
            "macro_chain": 0.25,
            "investment_trends": 0.20,
            "asset_breakdowns": 0.20,
        }
        composite = sum(scores.get(k, 0.0) * w for k, w in weights.items())

        grade = (
            "A"
            if composite >= 80
            else "B"
            if composite >= 60
            else "C"
            if composite >= 40
            else "D"
        )

        result = {
            "composite_score": round(composite, 1),
            "grade": grade,
            "dimension_scores": {k: round(v, 1) for k, v in scores.items()},
            "issues": issues,
        }
        logger.info(
            f"Report quality: {grade} ({composite:.1f}/100), issues={len(issues)}"
        )
        return result


__all__ = ["ReportEvaluator"]
