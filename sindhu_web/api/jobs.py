from fastapi import APIRouter, HTTPException

from sindhu_web.jobs import job_manager

router = APIRouter()


@router.get("/api/jobs")
def list_jobs():
    return {"jobs": [j.to_dict() for j in job_manager.list_jobs()]}


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.to_dict()


@router.post("/api/jobs/{job_id}/pause")
def pause_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.control:
        job.control.pause()
    return {"ok": True}


@router.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.control:
        job.control.resume()
    return {"ok": True}


@router.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.control:
        job.control.stop()
    return {"ok": True}
