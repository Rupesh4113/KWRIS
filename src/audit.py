"""Correction Audit and Review Trail Tracking for KWRIS."""

from __future__ import annotations
import datetime
from typing import Any, Dict, List, Optional
import pandas as pd
from src.models import CorrectionProposal, ReviewStatus


class AuditTrailManager:
    """Manages the lifecycle of correction proposals, approvals, and audit trail records."""
    
    def __init__(self, proposals: Optional[List[CorrectionProposal]] = None):
        self.proposals: Dict[str, CorrectionProposal] = {}
        if proposals:
            for p in proposals:
                self.proposals[p.proposal_id] = p

    def add_proposal(self, proposal: CorrectionProposal) -> None:
        self.proposals[proposal.proposal_id] = proposal

    def add_proposals(self, proposals: List[CorrectionProposal]) -> None:
        for p in proposals:
            self.proposals[p.proposal_id] = p

    def approve_proposal(self, proposal_id: str, approved_val: Optional[float] = None, comment: str = "") -> bool:
        if proposal_id in self.proposals:
            p = self.proposals[proposal_id]
            p.review_status = ReviewStatus.APPROVED
            p.approved_value = approved_val if approved_val is not None else p.proposed_value
            p.reviewer_comment = comment
            return True
        return False

    def reject_proposal(self, proposal_id: str, comment: str = "") -> bool:
        if proposal_id in self.proposals:
            p = self.proposals[proposal_id]
            p.review_status = ReviewStatus.REJECTED
            p.reviewer_comment = comment
            return True
        return False

    def defer_proposal(self, proposal_id: str, comment: str = "") -> bool:
        if proposal_id in self.proposals:
            p = self.proposals[proposal_id]
            p.review_status = ReviewStatus.DEFERRED
            p.reviewer_comment = comment
            return True
        return False

    def approve_all(self, rule_filter: Optional[str] = None) -> int:
        count = 0
        for p in self.proposals.values():
            if rule_filter is None or p.rule_id == rule_filter:
                if p.review_status == ReviewStatus.PENDING:
                    p.review_status = ReviewStatus.APPROVED
                    p.approved_value = p.proposed_value
                    count += 1
        return count

    def get_proposals_list(self) -> List[CorrectionProposal]:
        return list(self.proposals.values())

    def to_dataframe(self) -> pd.DataFrame:
        """Export audit trail to a standardized DataFrame for reporting."""
        records = []
        for p in self.proposals.values():
            records.append({
                "proposal_id": p.proposal_id,
                "station_id": p.station_id,
                "station_name": p.station_name,
                "observation_date": p.date,
                "original_rainfall_mm": p.original_value,
                "proposed_rainfall_mm": p.proposed_value,
                "approved_rainfall_mm": p.approved_value,
                "validation_rule": p.rule_id,
                "correction_method": p.method,
                "correction_reason": p.reason,
                "review_status": p.review_status.value,
                "reviewer_comment": p.reviewer_comment,
                "timestamp": p.created_at.strftime("%Y-%m-%d %H:%M:%S")
            })
            
        if not records:
            return pd.DataFrame(columns=[
                "proposal_id", "station_id", "station_name", "observation_date",
                "original_rainfall_mm", "proposed_rainfall_mm", "approved_rainfall_mm",
                "validation_rule", "correction_method", "correction_reason",
                "review_status", "reviewer_comment", "timestamp"
            ])
            
        return pd.DataFrame(records)
