from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import rasters as R

app = FastAPI(title="Pengerang EarthWatch", version="1.0.0-mvp")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


class CompareReq(BaseModel):
    before_id: str
    after_id: str


@app.get("/api/health")
def health():
    period = R.study_period()
    return {
        "ok": True,
        "study_period_complete": bool(period.get("complete")),
        "before_date": period.get("before_date"),
        "after_date": period.get("after_date"),
    }


@app.get("/api/rasters")
def list_rasters():
    summary = R.dataset_summary()
    items = [i for i in R.catalog() if "error" not in i]
    return {"dataset": summary, "count": len(items), "rasters": items}


@app.post("/api/rasters/compare")
def raster_compare(req: CompareReq):
    try:
        return R.validate_pair(req.before_id, req.after_id)
    except FileNotFoundError as e:
        raise HTTPException(404, f"Raster not found: {e}")


@app.get("/api/rasters/{raster_id}")
def raster_meta(raster_id: str):
    item = R.get_by_id(raster_id)
    if not item:
        raise HTTPException(404, "Raster not found")
    return item


@app.get("/api/rasters/{raster_id}/overlay.png")
def raster_overlay(raster_id: str):
    try:
        png = R.render_overlay_png(raster_id)
    except FileNotFoundError:
        raise HTTPException(404, "Raster not found")
    except Exception as e:
        raise HTTPException(500, f"Overlay render failed: {type(e).__name__}")
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
