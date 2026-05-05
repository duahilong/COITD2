import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.core.paths import APP_DIR
from app.services.binary_control_service import BinaryControlService
from app.services.config_service import ConfigService
from app.services.dashboard_service import DashboardService
from app.services.parameter_service import ParameterService

router = APIRouter()
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
config_service = ConfigService()
parameter_service = ParameterService(config_service=config_service)
binary_control_service = BinaryControlService(config_service=config_service)
dashboard_service = DashboardService(binary_control_service=binary_control_service)


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"summary": dashboard_service.summary()},
    )


@router.get("/binary-control", response_class=HTMLResponse)
def binary_control_page(request: Request) -> HTMLResponse:
    state = binary_control_service.get_state()
    runtime_context = config_service.get_runtime_context()
    state["binary_path"] = runtime_context.get("binary_path", "cfst")
    state["working_directory"] = runtime_context.get("working_directory", ".")
    state["command_preview"] = config_service.build_command_preview()
    latest_result = binary_control_service.latest_result_summary()
    return templates.TemplateResponse(
        request,
        "binary_control.html",
        {
            "request": request,
            "state": state,
            "latest_result": latest_result,
        },
    )


@router.post("/binary-control/{action}")
def binary_control(action: str) -> RedirectResponse:
    if action == "start":
        binary_control_service.start()
    elif action == "stop":
        binary_control_service.stop()
    elif action == "restart":
        binary_control_service.restart()
    return RedirectResponse(url="/binary-control", status_code=303)


@router.get("/parameters", response_class=HTMLResponse)
def parameters_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "parameters.html",
        {
            "request": request,
            **parameter_service.load_page_data(),
        },
    )


@router.get("/config", response_class=HTMLResponse)
def config_page(request: Request) -> HTMLResponse:
    master_config = config_service.load_master_config()
    command_preview = config_service.build_command_preview()
    return templates.TemplateResponse(
        request,
        "config.html",
        {
            "request": request,
            "config": master_config,
            "command_preview": command_preview,
        },
    )


@router.get("/config/raw", response_class=HTMLResponse)
def config_raw_page(request: Request) -> HTMLResponse:
    config = config_service.load_master_config()
    return templates.TemplateResponse(
        request,
        "config_raw.html",
        {
            "request": request,
            "config_json": json.dumps(config, ensure_ascii=False, indent=2),
            "server_error": "",
        },
    )


@router.post("/config/raw", response_class=HTMLResponse)
async def update_raw_config(request: Request) -> HTMLResponse:
    form = await request.form()
    config_json = str(form.get("config_json", ""))
    try:
        config = json.loads(config_json)
    except json.JSONDecodeError as exc:
        return templates.TemplateResponse(
            request,
            "config_raw.html",
            {
                "request": request,
                "config_json": config_json,
                "server_error": f"JSON 格式错误: {exc.msg}（第 {exc.lineno} 行，第 {exc.colno} 列）",
            },
            status_code=400,
        )

    validation_error = _validate_master_config(config)
    if validation_error:
        return templates.TemplateResponse(
            request,
            "config_raw.html",
            {
                "request": request,
                "config_json": config_json,
                "server_error": validation_error,
            },
            status_code=400,
        )

    config_service.save_master_config(config)
    return RedirectResponse(url="/config/raw", status_code=303)


@router.post("/config/binary/update")
async def update_binary_config(request: Request) -> JSONResponse:
    data = await request.json()
    config = config_service.load_master_config()
    binary_config = config.get("sections", {}).get("binary", {}).get("config", {})
    if "binary_path" in data:
        binary_config["binary_path"] = data["binary_path"]
    if "working_directory" in data:
        binary_config["working_directory"] = data["working_directory"]
    if "timeout_seconds" in data:
        binary_config["timeout_seconds"] = int(data["timeout_seconds"])
    config["sections"]["binary"]["config"] = binary_config
    config_service.save_master_config(config)
    return JSONResponse({"status": "ok", "command_preview": config_service.build_command_preview()})


@router.post("/config/parameter/update")
async def update_parameter(request: Request) -> JSONResponse:
    data = await request.json()
    key = data.get("key")
    enabled = data.get("enabled")
    value = data.get("value")
    if key:
        config_service.update_parameter(key, enabled=enabled, value=value)
        return JSONResponse({"status": "ok", "command_preview": config_service.build_command_preview()})
    return JSONResponse({"status": "error", "message": "Missing parameter key"}, status_code=400)


@router.post("/config/parameter/update_all")
async def update_all_parameters(request: Request) -> JSONResponse:
    data = await request.json()
    config = config_service.load_master_config()
    params = config.get("sections", {}).get("binary", {}).get("parameters", {})
    for key, updates in data.items():
        if key in params:
            if "enabled" in updates:
                params[key]["enabled"] = updates["enabled"]
            if "value" in updates:
                params[key]["value"] = updates["value"]
    config["sections"]["binary"]["parameters"] = params
    config_service.save_master_config(config)
    return JSONResponse({"status": "ok", "command_preview": config_service.build_command_preview()})


@router.post("/config/dns/update")
async def update_dns_config(request: Request) -> JSONResponse:
    data = await request.json()
    config = config_service.load_master_config()
    config["sections"]["dns"] = data
    config_service.save_master_config(config)
    return JSONResponse({"status": "ok"})


@router.post("/config/system/update")
async def update_system_config(request: Request) -> JSONResponse:
    data = await request.json()
    config = config_service.load_master_config()
    config["sections"]["system"] = data
    config_service.save_master_config(config)
    return JSONResponse({"status": "ok"})


@router.get("/config/preview", response_class=JSONResponse)
def config_preview() -> JSONResponse:
    return JSONResponse({
        "command_preview": config_service.build_command_preview(),
        "runtime_context": config_service.get_runtime_context(),
    })


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _validate_master_config(config: object) -> str | None:
    if not isinstance(config, dict):
        return "配置根节点必须是 JSON 对象。"
    if not isinstance(config.get("timestamps"), dict):
        return "缺少 timestamps 对象，无法记录配置更新时间。"
    if not isinstance(config.get("sections"), dict):
        return "缺少 sections 对象，无法识别配置分区。"

    sections = config["sections"]
    required_sections = {
        "binary": "测速二进制配置",
        "dns": "DNS 推送配置",
        "system": "系统配置",
    }
    for key, label in required_sections.items():
        if not isinstance(sections.get(key), dict):
            return f"缺少 sections.{key} 对象：{label}。"

    binary = sections["binary"]
    if not isinstance(binary.get("config"), dict):
        return "缺少 sections.binary.config 对象。"
    if not isinstance(binary.get("parameters"), dict):
        return "缺少 sections.binary.parameters 对象。"

    system = sections["system"]
    if not isinstance(system.get("web"), dict):
        return "缺少 sections.system.web 对象。"

    return None
