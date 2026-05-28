# DeskAd AI Studio - 보안 가이드

이 문서는 2026-05-28 보안 강화 작업의 결과를 운영자/개발자가 한눈에 볼 수 있게 정리한다. 코드 변경의 근거(why)와 점검 절차(how to apply) 중심.

## 1. 위협 모델 요약

- 1순위: secret 노출 (PAT, LLM API key) - 화면/로그/git 히스토리로 새는 사고
- 2순위: 외부 노출 인터페이스 (Streamlit 8501) 무인증 접근
- 3순위: LLM/이미지 워커 prompt injection으로 시스템 프롬프트/내부 경로 누설
- 4순위: 업로드 파일/path traversal로 임의 파일 읽기/쓰기
- 5순위: 모델 워커(ComfyUI/Ollama) 포트가 외부에 열려 임의 추론/대량 요청

## 2. 적용된 코드/운영 변경

### 2-1. Secret redaction 단일 출처

- `backend/security.py`
  - `SENSITIVE_ENV_KEYS`: 보호 대상 환경변수 목록 (GITHUB_TOKEN, *_API_KEY, *_TOKEN, *_SECRET, *_PASSWORD 패턴 포함)
  - `_TOKEN_SHAPED_PATTERNS`: 토큰 모양의 문자열(ghp_, github_pat_, sk-, sk-ant-, hf_, Bearer ...) 정규식
  - `mask_value()`: 값 대신 `"set"` / `"missing"`만 반환
  - `redact_mapping()`: dict 안의 sensitive key를 한 번에 마스킹
  - `SecretLogFilter` + `install_secret_log_filter()`: root / uvicorn / httpx / requests / streamlit 로거에 redaction filter 부착. 환경변수 값과 토큰 모양 문자열을 자동으로 `[REDACTED]`로 치환.
- `backend/main.py`가 import 시점에 `install_secret_log_filter()` 호출 → 모든 응답/로그 경로에서 같은 정책.
- `backend/config.py`의 `redacted_settings()`도 `mask_value()`를 통과해 `/health` 응답에 secret 길이/값이 절대 새지 않는다.

### 2-2. 입력 검증 & prompt injection 방어

- `backend/main.py` Pydantic 모델
  - `AdContentRequest`: product_name 80, target_customer 120, selling_point 240, extra_request 400 등 모든 텍스트 필드에 `max_length`
  - `image_ratio`: `^(1:1|4:5|16:9)$` pattern
  - `image_job_id`: `^[A-Za-z0-9_\-]*$` + max_length 64 → path traversal 차단
  - `UploadedModelRequest.filename`: `^[^/\\\x00]+$` + max_length 255 → 슬래시/널바이트 차단
- `backend/ai.py`
  - `sanitize_user_text(value, limit)`: 제어문자 strip + whitespace 정규화 + 길이 trunc
  - `_ad_context()` / `build_image_prompt()` 모든 사용자 값에 사전 적용
  - `_system_prompt()`에 명시적 보안 규칙: 시스템 프롬프트/환경 변수/API 키/토큰/내부 경로 노출 금지, "이전 지시 무시" 같은 우회 요청 거부, JSON 외 출력 금지

### 2-3. CORS / 외부 노출

- `backend/main.py`의 `CORSMiddleware`가 환경변수 화이트리스트(`DESKAD_CORS_ORIGINS`)에서만 동작
  - 기본값(비어 있음) = CORS 미들웨어 자체를 등록하지 않음 → 외부 origin은 차단된다.
  - `allow_methods = ["GET","POST"]`, `allow_headers = ["Authorization","Content-Type"]`로 좁힘
  - wildcard `*` 지원 안 함
- 모델 워커 바인딩(2026-05-28 19:00 기준):
  - FastAPI 8010: `127.0.0.1` ✓
  - ComfyUI 8188: `127.0.0.1` ✓
  - Ollama 11434: `127.0.0.1` ✓
  - Streamlit 8501: `0.0.0.0` → **외부 공개**. GCP firewall로 회사 IP만 허용하거나 nginx basic auth 권장(§5).
- `start.sh`의 preflight가 ComfyUI/Ollama 외부 바인딩을 감지하면 warn 출력.

### 2-4. 파일 권한

- `start.sh` preflight에서 자동 적용:
  - `.env`가 600 이외 권한이면 600으로 잠금
  - `data/runtime/*.jsonl`을 600으로 잠금
- `backend/job_store.py`가 jsonl을 처음 생성할 때 즉시 `chmod 0o600`

### 2-5. Pre-commit secret scan

- `tools/scan_secrets.py`: stdlib만 사용. 패턴은 `backend/security.py`와 공유.
  - 인자 없으면 staged 파일만, `--all`이면 tracked 전체
  - `.env*` 파일은 placeholder 값 외 모든 KV에 alert
  - 값을 절대 출력하지 않고 path:line + reason만 표시
- `tools/git-hooks/pre-commit`: scan_secrets.py를 호출, 0이 아니면 commit 차단
- `start.sh` preflight가 `.git/hooks/pre-commit`이 없으면 자동 symlink 설치

### 2-6. .gitignore 강화

```text
.env
.env.*
!.env.example
*.pem *.key *.crt *.p12
*_secret*
*_token*
.netrc .npmrc
*.bak *.swp *.swo *~

deskad_keyboard_demo/data/runtime/
```

## 3. 운영자 체크리스트

매일 또는 새 환경 시작 시:

1. `stat -c '%a' deskad_keyboard_demo/.env` → `600`
2. `find deskad_keyboard_demo/data/runtime -name '*.jsonl' -exec stat -c '%n %a' {} +` → 모두 `600`
3. `ss -ltn | awk '$4 ~ /:(8010|8188|11434)$/'` → 모두 `127.0.0.1`로 시작
4. `python deskad_keyboard_demo/tools/scan_secrets.py --all` → exit 0
5. `git config --get core.hooksPath` 또는 `.git/hooks/pre-commit` 심볼릭 링크 확인

## 4. 사고 대응 - secret 노출 시

1. **즉시 revoke** - 노출된 토큰의 종류별 페이지:
   - GitHub classic PAT: https://github.com/settings/tokens
   - GitHub fine-grained PAT: https://github.com/settings/personal-access-tokens
   - OpenAI: https://platform.openai.com/api-keys
   - HuggingFace: https://huggingface.co/settings/tokens
2. **사용 흔적 점검** - GitHub security log, OpenAI usage dashboard, HF token activity
3. **재발급 + .env 교체** - 값을 화면에 띄우지 않는 방법:
   ```bash
   cd /home/leetaeho/ai_07_high/deskad_keyboard_demo
   read -s -p "New TOKEN: " T && \
     sed -i.bak -E "s|^GITHUB_TOKEN=.*$|GITHUB_TOKEN=${T}|" .env && \
     unset T
   chmod 600 .env
   shred -u .env.bak    # 백업 파일 안전 삭제
   ```
4. **git 히스토리에 새 적이 있는지 검사**:
   ```bash
   python deskad_keyboard_demo/tools/scan_secrets.py --all
   ```
   히트가 나면 해당 커밋이 푸시 전이면 amend 또는 reset --soft. 푸시 후라면 `git filter-repo`로 cleanup + remote 강제 푸시 + 협업자에 알림.

## 5. 외부 공개되는 Streamlit(8501) 보호 - 적용 완료 (2026-05-28)

이중 잠금이 적용된 상태.

### Layer 1: nginx basic auth + self-signed HTTPS (적용 완료)

- 패키지: `nginx 1.24.0`, `apache2-utils`
- 인증서: `/etc/nginx/ssl/deskad.crt` (self-signed, CN=34.27.86.182, 10년 유효)
- 키:    `/etc/nginx/ssl/deskad.key` (root:root 0600)
- htpasswd: `/etc/nginx/.deskad_htpasswd` (root:www-data 0640, bcrypt)
- 설정: `/etc/nginx/sites-enabled/deskad`
  - 8443/tcp HTTPS, TLSv1.2+TLSv1.3, HIGH cipher
  - `Strict-Transport-Security`, `X-Frame-Options DENY`, `X-Content-Type-Options nosniff`, `Referrer-Policy strict-origin-when-cross-origin`
  - basic auth realm "DeskAd AI Studio"
  - `/` 와 `/_stcore/stream` 둘 다 127.0.0.1:8501로 WebSocket upgrade 프록시
- Streamlit listen: `127.0.0.1:8501` (start.sh의 `FRONTEND_HOST`로 잠금. `DESKAD_STREAMLIT_HOST=0.0.0.0` 환경변수로 임시 해제 가능, 평소엔 사용 금지)
- Streamlit 추가 옵션: `--server.enableCORS false --server.enableXsrfProtection true`

비밀번호 갱신 (echo OFF, 한 줄):

```bash
sudo htpasswd -B /etc/nginx/.deskad_htpasswd deskad
# 추가 사용자 만들기:  sudo htpasswd -B /etc/nginx/.deskad_htpasswd <new_user>
# 사용자 삭제:        sudo htpasswd -D /etc/nginx/.deskad_htpasswd <user>
# 변경 후 reload 필요 없음 (nginx가 매 요청마다 파일 읽음)
```

### Layer 2: GCP firewall IP allowlist (사용자가 직접 적용)

VM 안의 서비스 계정은 compute scope가 없어 자동화 불가. 본인 PC/Cloud Shell에서 본인 계정 인증 후 실행:

```bash
# 1) 프로젝트 선택
gcloud config set project sprint-ai-chunk3-01

# 2) 본인 노트북/공유기 외부 IP 확인 (현재 SSH 세션에서 잡힌 IP: 112.162.29.176)
MY_IP=$(curl -s ifconfig.me)
echo "$MY_IP"

# 3) 8443 (HTTPS) 만 본인 IP에서 허용
gcloud compute firewall-rules create deskad-https-allow \
  --direction=INGRESS --action=ALLOW \
  --rules=tcp:8443 \
  --source-ranges="${MY_IP}/32" \
  --priority=900

# 4) 기존 8501 외부 공개 규칙 정리 (있다면)
gcloud compute firewall-rules list --filter="allowed.ports~8501" --format="value(name)" \
  | while read rule; do
      [ -n "$rule" ] && gcloud compute firewall-rules delete "$rule" --quiet
    done
```

또는 GCP Console:
- VPC 네트워크 > 방화벽 > 규칙 만들기
- 이름 `deskad-https-allow` / 방향 `수신` / 대상 `모든 인스턴스`
- 소스 IPv4: 본인 IP/32 (예: 112.162.29.176/32)
- 프로토콜/포트: `tcp:8443`

IP가 바뀌면 (KT 망 등) 위 명령의 `--source-ranges` 만 다시 update:
```bash
gcloud compute firewall-rules update deskad-https-allow --source-ranges=<new-ip>/32
```

### 접속 URL

- 외부: `https://34.27.86.182:8443` (브라우저가 self-signed cert 경고 → "고급 → 진행" 한 번 확인)
- 로컬: `http://127.0.0.1:8501` (VM 내부 SSH에서만)

### 운영 점검

```bash
# nginx 상태
sudo systemctl status nginx

# 잘못된 자격증명으로 접근 - 401 받아야 정상
curl -sk -o /dev/null -w "%{http_code}\n" https://127.0.0.1:8443/

# 올바른 자격증명 - 200
curl -sk -u deskad:<password> -o /dev/null -w "%{http_code}\n" https://127.0.0.1:8443/

# 인증서 만료일
echo | openssl s_client -connect 127.0.0.1:8443 2>/dev/null | openssl x509 -noout -dates
```

## 6. 자동 점검 명령

```bash
# 한 줄로 모든 점검:
( cd /home/leetaeho/ai_07_high/deskad_keyboard_demo && \
  python tools/scan_secrets.py --all && \
  stat -c '%n %a' .env data/runtime/*.jsonl 2>/dev/null && \
  ss -ltn | awk '$4 ~ /:(8010|8188|11434|8501)$/' )
```

기대 출력:
- scan_secrets: `clean (N file(s) scanned).`
- .env: 600
- jsonl: 600
- 8010 / 8188 / 11434: 127.0.0.1
- 8501: 0.0.0.0 → nginx로 보호한 경우 127.0.0.1
