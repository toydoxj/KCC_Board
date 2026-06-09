"""FastAPI 앱 엔트리포인트."""

import os
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.schemas import (
  BoardListResponse,
  BoardPropertyData,
  BoltListResponse,
  BoltMaterialData,
  ErrorPayload,
  ErrorResponse,
  HealthData,
  HealthResponse,
  StudListResponse,
  StudMethodData,
  StudMethodListResponse,
  StudSectionData,
  WallCheckRequestPayload,
  WallCheckResponse,
  WallCheckResultData,
)
from backend.engine.calculator import calculate_wall_check
from backend.engine.repository import JsonSeedRepository, MaterialRepository, RepositoryLookupError, SqliteRepository


ROOT_DIR = Path(__file__).resolve().parents[2]


def create_app(repository: MaterialRepository | None = None) -> FastAPI:
  app = FastAPI(title="KCC Board API", version="0.1.0")
  app.state.repository = repository or _default_repository()
  app.add_middleware(
    CORSMiddleware,
    allow_origins=[
      "http://127.0.0.1:3000",
      "http://localhost:3000",
      "http://127.0.0.1:3001",
      "http://localhost:3001",
      "kcc-board://kcc-board",
      "null",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
  )

  @app.exception_handler(RequestValidationError)
  async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
  ) -> JSONResponse:
    return _error_response(
      status_code=422,
      code="VALIDATION_ERROR",
      message=f"요청 형식이 올바르지 않습니다. 오류 수: {len(exc.errors())}",
    )

  @app.exception_handler(RepositoryLookupError)
  async def lookup_exception_handler(request: Request, exc: RepositoryLookupError) -> JSONResponse:
    return _error_response(status_code=400, code="LOOKUP_ERROR", message=str(exc))

  @app.exception_handler(ValueError)
  async def value_exception_handler(request: Request, exc: ValueError) -> JSONResponse:
    return _error_response(status_code=400, code="CALCULATION_ERROR", message=str(exc))

  @app.get("/api/health", response_model=HealthResponse)
  def health() -> HealthResponse:
    return HealthResponse(data=HealthData(status="ok"))

  @app.post("/api/check", response_model=WallCheckResponse)
  def check(payload: WallCheckRequestPayload, request: Request) -> WallCheckResponse:
    repo = cast(MaterialRepository, request.app.state.repository)
    result = calculate_wall_check(payload.to_engine(), repo)
    return WallCheckResponse(data=WallCheckResultData.from_engine(result))

  @app.get("/api/db/boards", response_model=BoardListResponse)
  def list_boards(request: Request) -> BoardListResponse:
    repo = cast(MaterialRepository, request.app.state.repository)
    return BoardListResponse(data=[BoardPropertyData.from_repository(board) for board in repo.list_board_catalog()])

  @app.get("/api/db/studs", response_model=StudListResponse)
  def list_studs(request: Request) -> StudListResponse:
    repo = cast(MaterialRepository, request.app.state.repository)
    return StudListResponse(data=[StudSectionData.from_repository(stud) for stud in repo.list_studs()])

  @app.get("/api/db/stud-methods", response_model=StudMethodListResponse)
  def list_stud_methods(request: Request) -> StudMethodListResponse:
    repo = cast(MaterialRepository, request.app.state.repository)
    return StudMethodListResponse(
      data=[StudMethodData.from_repository(stud_method) for stud_method in repo.list_stud_methods()],
    )

  @app.get("/api/db/bolts", response_model=BoltListResponse)
  def list_bolts(request: Request) -> BoltListResponse:
    repo = cast(MaterialRepository, request.app.state.repository)
    return BoltListResponse(data=[BoltMaterialData.from_repository(bolt) for bolt in repo.list_bolt_materials()])

  return app


def _default_repository() -> MaterialRepository:
  seed_dir = Path(os.environ.get("KCC_BOARD_SEED_DIR", str(ROOT_DIR / "data/seed")))
  if os.environ.get("KCC_BOARD_REPOSITORY", "").lower() == "json":
    return JsonSeedRepository(seed_dir)

  sqlite_path = Path(os.environ.get("KCC_BOARD_SQLITE_PATH", str(ROOT_DIR / "data/local/materials.sqlite3")))
  if sqlite_path.exists():
    return SqliteRepository(sqlite_path)
  return JsonSeedRepository(seed_dir)


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
  body = ErrorResponse(error=ErrorPayload(code=code, message=message))
  return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


app = create_app()
