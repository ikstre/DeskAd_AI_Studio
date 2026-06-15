# DeskAd 배포 가이드 — Docker (Phase 1: 앱 티어)

FastAPI 백엔드 + Streamlit 프론트엔드(앱 티어)를 Docker로 띄우는 절차입니다. 앱 티어는
**CPU-only**(`requirements.txt`에 torch/transformers 없음)이고, GPU 작업(LLM·이미지 생성)은
**외부 GPU 워커를 HTTP로 호출**합니다. 따라서 이 단계에서 GPU 워커는 **호스트에 그대로** 두고
컨테이너는 네트워크로만 연결합니다(GPU 워커 컨테이너화는 Phase 2).

> 인프라 고유값(예: `<VM_IP>`)은 자리표시자입니다. 실제 IP/토큰/비밀번호는 커밋하지 마세요.

---

## 1. 구성 개요

| 서비스 | 내용 | 호스트 바인딩 |
|--------|------|---------------|
| `backend` | uvicorn `backend.main:app` | `127.0.0.1:8010` |
| `frontend` | Streamlit `streamlit_app.py` | `127.0.0.1:8501` |
| (호스트) nginx | basic auth + TLS, `127.0.0.1:8501`로 프록시 | `:8443` (외부) |
| (호스트) GPU 워커 | ComfyUI(8188) · Omni vision(11601) · Omni image(11602) · SEED(11501) · Ollama(11434) | `127.0.0.1` 전용 |

- 두 컨테이너 모두 호스트 `127.0.0.1`에만 바인딩 → 직접 외부 노출 없음(보안 정책 유지, `docs/security.md` §5).
- 프론트엔드는 컨테이너 네트워크에서 `http://backend:8010`(서비스명)으로 백엔드를 호출합니다(`DESKAD_API_BASE`).

관련 파일: `Dockerfile`, `.dockerignore`, `docker-compose.yml`.

---

## 2. 사전 준비

1. **Docker Engine + Compose 플러그인** 설치(`docker compose version`으로 확인). `sudo` 없이 쓰려면 `sudo usermod -aG docker $USER` 후 재로그인(아니면 `sudo docker …`로 실행).
2. **`.env` 작성** — 이미지에 굽지 않고 런타임 주입합니다.
   ```bash
   cd deskad_keyboard_demo
   cp .env.example .env
   # 로그인/가입코드/엔진 키·워커 URL 등 입력
   ```
3. **GPU 워커는 호스트에서 기동**되어 있어야 GPU 경로(local/hyperclova)가 동작합니다.
   키·워커가 없어도 앱은 폴백(템플릿 문구 + SVG 일러스트)으로 동작합니다.

---

## 3. 빌드 & 실행

> **검증됨(2026-06-15)**: 이 VM에서 `docker compose build` 성공(이미지 `deskad-app:latest`, 195MB, CPU-only). 컨테이너 단독 기동 시 `/health`·`/render/keyboard-preview`(키·GPU 없이 GLB) 200 확인. `.env`를 이미지에 굽지 않아 단독 기동 시 설정은 기본값으로 뜬다.
>
> **컷오버 주의**: 호스트에서 `start.sh`로 띄운 기존 앱이 `8010`/`8501`을 점유 중이면 컨테이너가 같은 포트를 바인딩하지 못한다. 컨테이너로 전환할 땐 먼저 호스트 앱을 내려라.
> ```bash
> ss -ltnp | grep -E ':8010|:8501'   # 점유 확인
> bash start.sh --stop               # 호스트 앱 중지 후 compose 기동
> ```

```bash
cd deskad_keyboard_demo
docker compose up -d --build

# 상태/로그
docker compose ps
docker compose logs -f backend
```

검증:

```bash
curl -fsS http://127.0.0.1:8010/health        # {"status":"ok"} 류
curl -fsS http://127.0.0.1:8501/ >/dev/null   # 프론트엔드 응답
# 브라우저: https://<VM_IP>:8443  (호스트 nginx 경유)
```

> 호스트 계정 UID가 1000이 아니면 bind 마운트 쓰기 권한을 위해 빌드 시 UID/GID를 맞추세요.
> ```bash
> docker compose build --build-arg UID=$(id -u) --build-arg GID=$(id -g)
> ```

---

## 4. 호스트 GPU 워커 연결 (중요)

컨테이너 안에서 `127.0.0.1`은 **컨테이너 자신**을 가리킵니다. `.env`의 워커 URL이
`http://127.0.0.1:<port>`이면 호스트 워커에 닿지 않습니다. 둘 중 하나로 해결합니다.

- **(권장) `.env`의 `*_BASE_URL`을 `host.docker.internal`로** 변경
  ```ini
  LOCAL_LLM_BASE_URL=http://host.docker.internal:11434/v1
  HYPERCLOVA_BASE_URL=http://host.docker.internal:11501/v1
  HYPERCLOVA_VISION_BASE_URL=http://host.docker.internal:11601/v1
  HYPERCLOVA_IMAGE_BASE_URL=http://host.docker.internal:11602/v1
  COMFYUI_BASE_URL=http://host.docker.internal:8188
  ```
- 또는 `docker-compose.yml`의 `backend.environment`에서 동일 키를 덮어쓰기(주석 해제).

`docker-compose.yml`은 `extra_hosts: ["host.docker.internal:host-gateway"]`로 호스트를 해석합니다(Linux).

---

## 5. 볼륨 & 영속성

| 마운트 | 용도 |
|--------|------|
| `./data/runtime:/app/data/runtime` | 세션·비동기 이미지 잡(jsonl)·`users.json` 등 쓰기 상태 |
| `./static:/app/static` | 업로드/생성 GLB·포스터 (프론트가 model-viewer로 읽음) |
| `/opt/shared_data`, `/opt/shared_model` | (선택) 공유 라이브러리 기능 사용 시. 모델 weight는 굽지 말고 마운트 |

- 생성물(`static/`)과 런타임(`data/runtime/`)은 `.dockerignore`로 이미지에서 제외됩니다.
- 보안: `data/runtime`의 비밀 파일은 호스트에서 `0600` 권한을 유지하세요(`docs/security.md`).

---

## 6. 비밀 주입

- 실제 `.env`는 추적/커밋하지 않습니다. compose `env_file: .env`로 **런타임 주입**.
- `.dockerignore`가 `.env`/`.env.*`를 제외하므로 이미지에 비밀이 들어가지 않습니다(`.env.example`만 포함).
- `/security/config`는 키의 설정/미설정 상태만 반환하고 값은 노출하지 않습니다.

---

## 7. 외부 노출 (nginx)

기존 호스트 nginx(`:8443`, basic auth + self-signed TLS)를 그대로 사용합니다. 업스트림이
`127.0.0.1:8501`(프론트엔드 컨테이너 게시 포트)이므로 설정 변경이 거의 없습니다. WebSocket
경로(`/_stcore/stream`) 프록시는 `docs/security.md` §5 설정을 따릅니다.

---

## 8. 운영

```bash
docker compose restart backend     # 백엔드만 재시작 (start.sh --restart 대응)
docker compose down                # 종료 (볼륨은 보존)
docker compose up -d --build       # 코드 변경 반영 후 재기동
```

- 백엔드 코드를 고쳤다면 라이브 검증 전 `docker compose up -d --build`로 이미지를 갱신해야
  새 코드로 검증됩니다(uvicorn은 기동 시점 코드를 고정).

---

## 9. `GPU_WORKER_MODE` 주의

- 컨테이너 기본값은 **`always_on`**: 앱이 워커를 직접 띄우지 않고 base URL로 호출만 합니다.
- 호스트 단일 실행에서 쓰던 `exclusive`(켜기 전 경쟁 워커 종료)는 **앱이 워커 수명주기를 직접
  관리**하는 전제라, 컨테이너(`systemctl`/`Popen` 불가)에서는 적합하지 않습니다. 컨테이너에서는
  `always_on`을 유지하고 워커 기동/VRAM 조정은 호스트에서 관리하세요.

---

## 10. Phase 2 (예고) — GPU 워커 컨테이너화

`nvidia-container-toolkit` + `--gpus`/compose `deploy.resources`로 워커를 컨테이너화할 수
있으나, 단일 L4(24GB) VRAM 경합과 Omni 이미지 서버의 vendored diffusers/transformers shim
패키징 난도 때문에 별도 작업으로 분리합니다. 모델 weight는 항상 **볼륨 마운트**(이미지에 굽지 않음).
