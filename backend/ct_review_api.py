"""Strict loopback API for CT-only batches, live review and immutable output."""
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .ct_review import CTReview


class BatchInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    model_ids: list[str] = Field(min_length=1, max_length=4)
    confirmed: bool


class SnapshotInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    batch_id: str | None = None
    include_report: bool = False
    comparison_id: str | None = None


def create_ct_review_router(store, analysis):
    router = APIRouter(prefix='/api')
    service = CTReview(store, analysis)

    def call(function, *args):
        try:
            return function(*args)
        except KeyError:
            raise HTTPException(404, '대상 CT/분석 기록을 찾을 수 없습니다.')
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc))
        except OSError:
            raise HTTPException(422, 'CT 원본이나 결과 파일을 확인하지 못했습니다. 정상 결과로 취급하지 않습니다.')

    @router.get('/series/{series_id}/ct-plan')
    def plan(series_id: str):
        return call(service.plan, series_id)

    @router.post('/series/{series_id}/ct-batches', status_code=201)
    def start(series_id: str, value: BatchInput):
        return call(service.start, series_id, value.model_ids, value.confirmed)

    @router.get('/series/{series_id}/ct-batches')
    def batches(series_id: str):
        return {'items': call(service.batches, series_id)}

    @router.get('/ct-batches/{identifier}')
    def batch(identifier: str):
        return call(service.batch, identifier)

    @router.post('/ct-batches/{identifier}/cancel')
    def cancel(identifier: str):
        return call(service.cancel, identifier)

    @router.get('/series/{series_id}/ct-review')
    def review(series_id: str, batch_id: str | None = None, include_report: bool = False, comparison_id: str | None = None):
        return call(service.view, series_id, batch_id, include_report, comparison_id)

    @router.post('/series/{series_id}/ct-reviews', status_code=201)
    def snapshot(series_id: str, value: SnapshotInput):
        return call(service.snapshot, series_id, value.batch_id, value.include_report, value.comparison_id)

    @router.get('/series/{series_id}/ct-reviews')
    def history(series_id: str):
        series = call(service.row, 'series', series_id)
        # Older report-based snapshots keep their schema and remain available
        # through existing summary APIs. Poll only compact metadata for the most
        # recent 20 CT snapshots, not every historical candidate/weight payload.
        items = []
        with store.connect() as c:
            for row in c.execute('SELECT * FROM summary_versions WHERE study_id=? ORDER BY created_at DESC,rowid DESC', (series['study_id'],)):
                payload = json.loads(row['payload'])
                review = payload.get('integrated_review', {})
                if review.get('series_id') == series_id:
                    items.append({'id': row['id'], 'study_id': row['study_id'], 'created_at': row['created_at'],
                                  'status': review['status'], 'proposal_count': review['proposal_count'],
                                  'include_report': review['report_context']['enabled']})
                    if len(items) == 20:
                        break
        return {'items': items}

    return router
