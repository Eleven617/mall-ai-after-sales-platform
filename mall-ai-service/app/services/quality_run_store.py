"""Small in-memory store for developer-reviewed quality runs.

Quality runs are not customer or business records.  They intentionally remain
process-local so a restart clears only evaluation history, never orders,
returns, handoffs, Outbox events, Redis conversations, or production traces.
"""

from collections import OrderedDict
from threading import RLock

from app.schemas.agent_ops import EvaluationProfileExperiment
from app.schemas.quality import EvalCase, QualityEvaluationRun, QualityReviewStatus


class QualityRunStore:
    def __init__(self, max_runs: int = 20) -> None:
        self._max_runs = max_runs
        self._runs: OrderedDict[str, QualityEvaluationRun] = OrderedDict()
        self._fixtures: OrderedDict[str, tuple[EvalCase, ...]] = OrderedDict()
        self._experiments: OrderedDict[str, EvaluationProfileExperiment] = OrderedDict()
        self._lock = RLock()

    def save(
        self,
        run: QualityEvaluationRun,
        *,
        fixtures: list[EvalCase] | tuple[EvalCase, ...] | None = None,
    ) -> QualityEvaluationRun:
        with self._lock:
            self._runs[run.run_id] = run
            self._runs.move_to_end(run.run_id)
            if fixtures is not None:
                self._fixtures[run.run_id] = tuple(
                    case.model_copy(deep=True) for case in fixtures
                )
                self._fixtures.move_to_end(run.run_id)
            while len(self._runs) > self._max_runs:
                evicted_id, _ = self._runs.popitem(last=False)
                self._fixtures.pop(evicted_id, None)
            while len(self._fixtures) > self._max_runs:
                self._fixtures.popitem(last=False)
        return run

    def latest(self) -> QualityEvaluationRun | None:
        with self._lock:
            return next(reversed(self._runs.values()), None) if self._runs else None

    def get(self, run_id: str) -> QualityEvaluationRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def fixtures_for(self, run_id: str) -> tuple[EvalCase, ...] | None:
        with self._lock:
            fixtures = self._fixtures.get(run_id)
            if fixtures is None:
                return None
            return tuple(case.model_copy(deep=True) for case in fixtures)

    def set_case_review(
        self,
        *,
        run_id: str,
        case_id: str,
        review_status: QualityReviewStatus,
    ) -> QualityEvaluationRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            changed = False
            cases = []
            for case in run.cases:
                if case.case_id == case_id:
                    cases.append(case.model_copy(update={"review_status": review_status}))
                    changed = True
                else:
                    cases.append(case)
            if not changed:
                return None
            updated = run.model_copy(update={"cases": cases})
            self._runs[run_id] = updated
            self._runs.move_to_end(run_id)
            return updated

    def save_experiment(
        self, experiment: EvaluationProfileExperiment
    ) -> EvaluationProfileExperiment:
        with self._lock:
            self._experiments[experiment.experiment_id] = experiment
            self._experiments.move_to_end(experiment.experiment_id)
            while len(self._experiments) > self._max_runs:
                self._experiments.popitem(last=False)
        return experiment

    def latest_experiment(self) -> EvaluationProfileExperiment | None:
        with self._lock:
            return (
                next(reversed(self._experiments.values()), None)
                if self._experiments
                else None
            )


quality_run_store = QualityRunStore()
