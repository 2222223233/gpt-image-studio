"""Local image generation UI. Python 3.10+, standard library only."""
import argparse
import base64
import binascii
import json
import mimetypes
import re
import struct
from pathlib import Path
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler
import webbrowser

VERSION = "1.0.1"
ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
IMAGE_DIR = ROOT / "generated"
TOKEN = secrets.token_urlsafe(32)
MAX_IMAGE = 40 * 1024 * 1024
MAX_RESPONSE = 180 * 1024 * 1024
MAX_REFERENCE = 20 * 1024 * 1024
MAX_REFERENCE_TOTAL = 40 * 1024 * 1024
MAX_REFERENCES = 16
MAX_LOCAL_REQUEST = ((MAX_REFERENCE_TOTAL + 2) // 3) * 4 + 1024 * 1024


class UserError(Exception):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fp.close()
        raise UserError("接口发生重定向。请填写服务商提供的最终 API 地址，避免密钥被转发。")


def read_limited(response, limit):
    data = response.read(limit + 1)
    if len(data) > limit:
        raise UserError("接口返回的数据过大，请减少图片数量或尺寸。")
    return data


def clean_url(value):
    value = str(value).strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise UserError("请填写完整的 API 根地址，例如 https://api.openai.com/v1。")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise UserError("远程 API 地址必须使用 HTTPS。")
    if parsed.path.endswith(("/images/generations", "/images/edits", "/models")):
        raise UserError("请填写 API 根地址（通常以 /v1 结尾），不要包含 /images/generations、/images/edits 或 /models。")
    return value


def credentials(data):
    key = str(data.get("api_key", "")).strip()
    if not key or any(c in key for c in "\r\n"):
        raise UserError("请先填写有效的 API Key。")
    return clean_url(data.get("base_url", "")), key


def multipart_body(payload, files):
    boundary = "----GPTImageStudio" + secrets.token_hex(24)
    parts = []
    for name, value in payload.items():
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode("utf-8"))
    field = "image" if len(files) == 1 else "image[]"
    for index, file in enumerate(files, 1):
        # Generated ASCII filenames avoid placing user-controlled text in MIME headers.
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="reference-{index}.{file["extension"]}"\r\nContent-Type: {file["mime"]}\r\n\r\n').encode("ascii"))
        parts.extend((file["raw"], b"\r\n"))
    parts.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def api_request(url, key, payload=None, timeout=600, files=None):
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json", "User-Agent": "GPTImageStudio/1.0.1"}
    body = None
    if files:
        body, headers["Content-Type"] = multipart_body(payload, files)
    elif payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=body, headers=headers)
    try:
        with build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            raw = read_limited(response, MAX_RESPONSE)
    except HTTPError as exc:
        with exc:
            raw = exc.read(8192).decode("utf-8", "replace")
        request_id = exc.headers.get("x-request-id") or exc.headers.get("request-id") or exc.headers.get("cf-ray")
        try:
            value = json.loads(raw)
            error = value.get("error", value)
            detail = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        except (ValueError, AttributeError):
            detail = raw[:1500]
        hints = {401: "API Key 无效或已过期。", 403: "账号没有权限，或服务商拒绝了请求。", 404: "接口路径或模型可能不受支持。", 429: "余额、配额或请求频率受到限制。"}
        hints.update({400: "服务商拒绝了请求参数，请检查尺寸、画质及规划强度。", 502: "服务商网关的上游调用失败。可能是临时故障、模型路由或参数兼容问题；不代表你的电脑不支持 4K。", 503: "服务商暂时不可用或繁忙。", 504: "服务商网关等待上游超时，本地延长超时不一定有效。"})
        if files and exc.code in (400, 404, 413, 415):
            hints[exc.code] = "服务商拒绝了图片编辑请求。请确认模型支持 /images/edits 和图片上传，并检查服务商的格式、张数与大小限制。"
        if exc.code in (502, 503, 504):
            detail += "\n程序没有自动重试或切换模型。请先查服务商记录，再决定重试；也可手动用同一模型的默认尺寸排查。"
        details = {"upstream_status": exc.code}
        if request_id:
            details["request_id"] = request_id.replace(key, "[已隐藏密钥]")
        raise UserError(f"HTTP {exc.code}：{hints.get(exc.code, '服务商返回错误。')}\n{detail}".replace(key, "[已隐藏密钥]"), details) from None
    except (TimeoutError, socket.timeout):
        raise UserError("请求超时。服务端可能仍在生成，重新提交可能再次计费；请先检查服务商记录。") from None
    except URLError as exc:
        raise UserError(f"无法连接 API：{exc.reason}".replace(key, "[已隐藏密钥]")) from None
    try:
        value = json.loads(raw)
    except ValueError:
        raise UserError("接口没有返回 JSON。请检查 API 地址是否正确。") from None
    if not isinstance(value, dict):
        raise UserError("接口返回格式不兼容：预期 JSON 对象。")
    if value.get("error"):
        raise UserError(str(value["error"])[:2000].replace(key, "[已隐藏密钥]"))
    return value


def validate_size(value):
    value = str(value).strip().lower().replace("×", "x")
    if not value or value == "auto":
        return value
    if not re.fullmatch(r"[0-9]{1,5}x[0-9]{1,5}", value):
        raise UserError("尺寸请填写 宽x高，例如 3840x2160；不要填写 4K。")
    width, height = map(int, value.split("x"))
    if min(width, height) <= 0 or width % 16 or height % 16:
        raise UserError("宽和高必须是正整数且为 16 的倍数，例如 3840×2160。")
    if max(width, height) > 3840:
        raise UserError("当前 GPT Image 尺寸规则要求每边不超过 3840；4K 横图请选择 3840×2160，不是 4096×4096。")
    if max(width, height) > 3 * min(width, height):
        raise UserError("宽高比必须在 1:3 到 3:1 之间。")
    if not 655360 <= width * height <= 8294400:
        raise UserError("总像素必须在 655,360–8,294,400 之间。3840×2160 为 4K UHD；3840×3840 超过限制。")
    return f"{width}x{height}"


def generation_payload(data):
    model = str(data.get("model", "")).strip()
    prompt = str(data.get("prompt", "")).strip()
    if not model or not prompt:
        raise UserError("请填写模型名称和图片描述。")
    if len(prompt) > 32000:
        raise UserError("图片描述不能超过 32,000 个字符。")
    payload = {"model": model, "prompt": prompt}
    size = validate_size(data.get("size", ""))
    if size:
        payload["size"] = size
    choices = {
        "quality": ("low", "medium", "high", "xhigh", "max", "auto"),
        "complexity": ("low", "medium", "high"),
        "output_format": ("png", "jpeg", "webp"),
        "background": ("auto", "opaque", "transparent"),
        "response_format": ("b64_json", "url"),
    }
    for name, allowed in choices.items():
        value = data.get(name)
        if value:
            if value not in allowed:
                raise UserError(f"参数 {name} 不受支持。")
            payload[name] = value
    if payload.get("background") == "transparent" and payload.get("output_format") == "jpeg":
        raise UserError("JPEG 不支持透明背景，请改选 PNG 或 WebP。")
    compression = data.get("output_compression")
    if compression not in (None, ""):
        if payload.get("output_format") not in ("jpeg", "webp"):
            raise UserError("压缩参数仅适用于 JPEG / WebP，请选择对应格式或留空压缩参数。")
        try:
            compression = int(str(compression))
        except ValueError:
            raise UserError("压缩参数必须是 0–100 的整数。") from None
        if not 0 <= compression <= 100:
            raise UserError("压缩参数必须是 0–100 的整数。")
        payload["output_compression"] = compression
    if data.get("n"):
        try:
            n = int(data["n"])
        except (ValueError, TypeError):
            raise UserError("图片数量必须为 1–4。") from None
        if n not in range(1, 5):
            raise UserError("图片数量必须为 1–4。")
        payload["n"] = n
    return payload


def image_dimensions(raw):
    """Read raster dimensions without decoding/resizing image data."""
    try:
        ext = image_extension(raw)
        if ext == "png" and raw[12:16] == b"IHDR":
            return struct.unpack(">II", raw[16:24])
        if ext == "gif":
            return struct.unpack("<HH", raw[6:10])
        if ext == "webp":
            pos = 12
            while pos + 8 <= len(raw):
                kind = raw[pos:pos + 4]
                size = int.from_bytes(raw[pos + 4:pos + 8], "little")
                chunk = raw[pos + 8:pos + 8 + size]
                if kind == b"VP8X" and len(chunk) >= 10:
                    return 1 + int.from_bytes(chunk[4:7], "little"), 1 + int.from_bytes(chunk[7:10], "little")
                if kind == b"VP8 " and len(chunk) >= 10 and chunk[3:6] == b"\x9d\x01\x2a":
                    w, h = struct.unpack("<HH", chunk[6:10])
                    return w & 0x3fff, h & 0x3fff
                if kind == b"VP8L" and len(chunk) >= 5 and chunk[0] == 0x2f:
                    bits = int.from_bytes(chunk[1:5], "little")
                    return (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
                pos += 8 + size + (size % 2)
        if ext == "jpg":
            pos = 2
            while pos < len(raw):
                if raw[pos] != 0xff:
                    return None
                while pos < len(raw) and raw[pos] == 0xff:
                    pos += 1
                marker = raw[pos]
                pos += 1
                if marker in (0xda, 0xd9):
                    break
                if marker in (0x01, *range(0xd0, 0xd9)):
                    continue
                size = int.from_bytes(raw[pos:pos + 2], "big")
                if size < 2 or pos + size > len(raw):
                    break
                if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
                    h, w = struct.unpack(">HH", raw[pos + 3:pos + 7])
                    return w, h
                pos += size
    except (IndexError, struct.error, UserError):
        pass
    return None


def image_extension(raw):
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "webp"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    raise UserError("返回内容不是可识别的 PNG、JPEG、WebP 或 GIF 图片。")


def reference_files(data):
    items = data.get("reference_images", [])
    if not isinstance(items, list) or len(items) > MAX_REFERENCES:
        raise UserError("参考图片必须是列表，最多 16 张。")
    files, total = [], 0
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or not isinstance(item.get("b64_json"), str):
            raise UserError(f"图{index} 的上传数据无效，请重新选择图片。")
        encoded = item["b64_json"]
        if len(encoded) > ((MAX_REFERENCE + 2) // 3) * 4:
            raise UserError(f"图{index} 超过本工具单张 20 MB 的限制。")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise UserError(f"图{index} 的图片编码无效，请重新选择。") from None
        total += len(raw)
        if len(raw) > MAX_REFERENCE or total > MAX_REFERENCE_TOTAL:
            raise UserError("本工具限制单张图片不超过 20 MB，全部参考图片合计不超过 40 MB。")
        try:
            ext = image_extension(raw)
        except UserError:
            raise UserError(f"图{index} 不是有效的 PNG、JPEG 或 WebP 图片。") from None
        if ext not in ("png", "jpg", "webp"):
            raise UserError(f"图{index} 格式不支持，请使用 PNG、JPEG 或 WebP。")
        dimensions = image_dimensions(raw)
        if not dimensions or min(dimensions) <= 0:
            raise UserError(f"图{index} 无法识别宽高，图片可能已损坏。")
        if dimensions[0] * dimensions[1] > 16777216:
            raise UserError(f"图{index} 超过本工具 16,777,216 像素的上传限制，请先缩小图片。")
        files.append({"raw": raw, "extension": ext, "mime": {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[ext], "width": dimensions[0], "height": dimensions[1]})
    return files


def prepare_request(data):
    payload = generation_payload(data)
    files = reference_files(data)
    endpoint = "/images/edits" if files else "/images/generations"
    summary = {k: v for k, v in payload.items() if k != "prompt"}
    summary["endpoint"] = endpoint
    if files:
        summary["reference_images"] = [{"number": i, "width": f["width"], "height": f["height"], "bytes": len(f["raw"])} for i, f in enumerate(files, 1)]
    return payload, files, endpoint, summary


def save_image(item):
    if not isinstance(item, dict):
        raise UserError("图片条目格式不兼容。")
    if item.get("b64_json"):
        try:
            raw = base64.b64decode(item["b64_json"], validate=True)
        except (ValueError, TypeError, binascii.Error):
            raise UserError("接口返回的 Base64 图片无效。") from None
    elif item.get("url"):
        url = item["url"]
        if not isinstance(url, str) or urlsplit(url).scheme not in ("https", "http"):
            raise UserError("接口返回的图片下载链接无效。")
        # No API credential is sent to the image host. Disable redirects here too.
        try:
            with build_opener(NoRedirect()).open(Request(url, headers={"User-Agent": "GPTImageStudio/1.0.1"}), timeout=90) as response:
                raw = read_limited(response, MAX_IMAGE)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise UserError("图片已生成，但下载失败。请查看服务商生成记录；重新生成可能再次计费。") from exc
    else:
        raise UserError("图片条目没有 b64_json 或 url 字段。")
    if len(raw) > MAX_IMAGE:
        raise UserError("单张图片超过 40 MB，未保存。")
    ext = image_extension(raw)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(4) + "." + ext
    (IMAGE_DIR / name).write_bytes(raw)
    dimensions = image_dimensions(raw)
    return {"url": "/generated/" + name, "name": name, "revised_prompt": item.get("revised_prompt", ""), "width": dimensions[0] if dimensions else None, "height": dimensions[1] if dimensions else None, "bytes": len(raw)}


def generate(data):
    base, key = credentials(data)
    payload, files, endpoint, request_summary = prepare_request(data)
    try:
        timeout = int(data.get("timeout", 600))
    except (TypeError, ValueError):
        raise UserError("超时时间应为 30–900 秒。") from None
    if not 30 <= timeout <= 900:
        raise UserError("超时时间应为 30–900 秒。")
    try:
        result = api_request(base + endpoint, key, payload, timeout, files=files)
    except UserError as exc:
        exc.details["parameters"] = request_summary
        raise
    items = result.get("data")
    if not isinstance(items, list) or not items:
        raise UserError(f"接口没有返回 data 图片列表。请确认该模型支持 {endpoint}。", {"parameters": request_summary})
    images, warnings = [], []
    for item in items:
        try:
            image = save_image(item)
            images.append(image)
            requested = payload.get("size")
            if image["width"] and requested and requested != "auto":
                actual = f'{image["width"]}x{image["height"]}'
                if actual != requested:
                    warnings.append(f"请求尺寸 {requested}，实际返回 {actual}。已保留服务商原图；程序没有放大或缩小图片。")
        except UserError as exc:
            warnings.append(str(exc).replace(key, "[已隐藏密钥]"))
    if not images:
        raise UserError("\n".join(warnings))
    return {"images": images, "warnings": warnings, "parameters": request_summary}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Do not log prompts or credentials.

    def send(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {"error": "无效的访问地址。"})
        path = unquote(urlsplit(self.path).path)
        if path == "/":
            return self.send(200, (WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path in ("/app.js", "/references.js"):
            return self.send(200, (WEB_DIR / path[1:]).read_bytes(), "application/javascript; charset=utf-8")
        if path.startswith("/generated/"):
            filename = path[len("/generated/"):]
            if not filename or any(c in filename for c in ("/", "\\", ":")) or filename.startswith("."):
                return self.send(404, {"error": "文件不存在。"})
            file = IMAGE_DIR / filename
            if file.is_file():
                return self.send(200, file.read_bytes(), mimetypes.guess_type(filename)[0] or "application/octet-stream")
        self.send(404, {"error": "文件不存在。"})

    def do_POST(self):
        expected_origin = f"http://127.0.0.1:{self.server.server_port}"
        if not self.valid_host() or self.headers.get("X-Studio-Token") != TOKEN or self.headers.get("Origin") not in (None, expected_origin):
            return self.send(403, {"error": "会话已失效，请用启动窗口中的完整链接打开页面。"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            limit = MAX_LOCAL_REQUEST if self.path in ("/api/generate", "/api/preview") else 256 * 1024
            if not 0 < length <= limit:
                self.close_connection = True
                return self.send(413, {"error": "上传请求为空或过大；参考图片合计最多 40 MB。"})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise UserError("请求格式错误。")
            if self.path == "/api/generate":
                response = generate(data)
            elif self.path == "/api/preview":
                _, _, _, summary = prepare_request(data)
                response = {"parameters": summary}
            elif self.path == "/api/models":
                base, key = credentials(data)
                result = api_request(base + "/models", key, timeout=30)
                models = result.get("data")
                if not isinstance(models, list):
                    raise UserError("模型列表格式不兼容；仍可手动填写模型名称。")
                response = {"models": sorted({item["id"] for item in models if isinstance(item, dict) and isinstance(item.get("id"), str)})}
            else:
                return self.send(404, {"error": "接口不存在。"})
            self.send(200, response)
        except (UserError, ValueError) as exc:
            self.send(400, {"error": str(exc), "details": getattr(exc, "details", {})})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send(500, {"error": "本地处理失败。请确认 generated 文件夹可写、磁盘空间充足，或检查服务商响应格式。"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version="GPT Image Studio " + VERSION)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=0, help="Local port (0 chooses an available port)")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        parser.error(f"Cannot start local server: {exc}")
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}/#{TOKEN}"
    print("GPT Image Studio is running. Keep this window open.\n" + url, flush=True)
    print("Images are saved in: " + str(IMAGE_DIR), flush=True)
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
