# 2026-06-11 최종 메서드 정리

## Streamlit 진입 흐름

| 파일 | 메서드 | 역할 |
| --- | --- | --- |
| `streamlit_app.py` | `go_next()` | 다음 단계로 이동할 때 필요한 렌더링 선행 작업을 연결한다. |
| `streamlit_app.py` | `go_previous()` | 현재 단계를 이전 단계로 되돌린다. |
| `ui/state.py` | `initialize_session_defaults()` | 앱 최초 진입 시 `session_state` 기본값을 채운다. |
| `ui/state.py` | `sync_step_from_sidebar()` | 사이드바 단계 선택값을 실제 작업 단계와 동기화하고, 필수 입력값 누락 시 이동을 막는다. |
| `ui/state.py` | `go_next_step()` | 다음 단계 이동을 처리하고, Step 1 필수값과 Step 3 모델 생성 조건을 확인한다. |
| `ui/state.py` | `missing_product_fields()` | 상품명, 판매가, 타깃 고객, 핵심 특징 중 비어 있는 필수값 목록을 반환한다. |

## API / 에러 메시지

| 파일 | 메서드 | 역할 |
| --- | --- | --- |
| `ui/api_client.py` | `load_env_file()` | `.env` 파일을 읽어 Streamlit 프로세스 환경 변수에 반영한다. |
| `ui/api_client.py` | `_api_error_message()` | API 연결 실패, 타임아웃, HTTP 오류를 사용자용 한국어 메시지로 변환한다. |
| `ui/api_client.py` | `api_get()` | FastAPI GET 요청을 보내고 실패 시 친화적인 오류 메시지를 발생시킨다. |
| `ui/api_client.py` | `api_post()` | FastAPI POST 요청을 보내고 실패 시 친화적인 오류 메시지를 발생시킨다. |
| `ui/api_client.py` | `fetch_security_config()` | 운영 진단용 보안/API 설정 요약을 가져온다. 현재는 진단 버튼을 눌렀을 때만 호출된다. |

## 공통 표시 / 포맷

| 파일 | 메서드 | 역할 |
| --- | --- | --- |
| `ui/formatting.py` | `format_price_display()` | 판매가를 화면 표시용 콤마 숫자로 정리한다. `180000`, `180,000`, `180000원` 모두 `180,000`으로 보인다. |
| `ui/components.py` | `render_campaign_studio_header()` | 상단 캠페인 브리프 영역을 렌더링한다. 상품명, 채널, 타깃, 가격, 톤을 요약해서 보여준다. |
| `ui/components.py` | `render_studio_status_cards()` | Step 4의 3D 씬, 광고 문구, 포스터 준비 상태 카드를 렌더링한다. |

## 사이드바 / 로딩 최적화

| 파일 | 메서드 | 역할 |
| --- | --- | --- |
| `ui/sidebar.py` | `_step_state_label()` | 각 단계가 완료, 진행 중, 대기 중인지 표시할 라벨을 계산한다. |
| `ui/sidebar.py` | `render_sidebar()` | 사이드바의 진행 요약, 단계 이동, 화면 모드, 고급 진단 영역을 렌더링한다. 진단 API는 첫 로드에서 호출하지 않고 사용자가 `진단 정보 불러오기`를 눌렀을 때만 호출한다. |

## Step 입력 / 광고 생성 흐름

| 파일 | 메서드 | 역할 |
| --- | --- | --- |
| `ui/context.py` | `build_step_ui_context()` | 단계별 입력 UI가 사용할 함수와 상수 dependency를 묶어 전달한다. Step 2~4 전용 함수는 lazy wrapper로 연결해 첫 화면 로드 시 불필요한 모듈 import를 줄인다. |
| `ui/context.py` | `_fetch_layout_ids()` 등 lazy wrapper | API, 3D 렌더링, 광고 생성, 모델 라이브러리 관련 함수를 실제 호출 시점에 import해서 초기 렌더링 부담을 낮춘다. |
| `ui_steps.py` | `_bind_product_widget_state()` | Streamlit 위젯용 임시 key와 실제 저장용 key를 연결해 단계 이동 시 입력값이 초기화되지 않게 한다. |
| `ui_steps.py` | `_sync_product_field()` | 임시 위젯 값을 실제 상품 정보 상태값에 반영한다. |
| `ui_steps.py` | `_normalize_price_input()` | 판매가 입력에서 숫자만 남기고 콤마 숫자로 저장한다. |
| `ui_steps.py` | `_ad_workflow_state()` | 광고 문구, 이미지 작업, 포스터 생성의 현재 완료/진행/실패 상태를 계산한다. |
| `ui_steps.py` | `_render_ad_workflow_cards()` | Step 4에서 광고 문구 → 이미지 작업 → 포스터 순서의 진행 카드를 보여준다. |
| `ui_steps.py` | `_set_ad_action_notice()` | 버튼 실행 후 rerun이 발생해도 사용자 메시지가 사라지지 않도록 세션에 알림을 저장한다. |
| `ui_steps.py` | `_render_ad_action_notice()` | 세션에 저장된 광고 작업 알림을 success/info/warning/error 형태로 표시한다. |
| `ui_steps.py` | `_image_job_feedback()` | 이미지 작업 job 상태를 success/info/warning/error 메시지로 변환한다. |
| `ui_steps.py` | `render_step_input_panel()` | 현재 단계에 맞는 입력 패널을 렌더링한다. |

## 광고 콘텐츠 / 결과 미리보기

| 파일 | 메서드 | 역할 |
| --- | --- | --- |
| `ui/ad_content.py` | `build_ad_payload()` | 상품 정보, 셋업 정보, 광고 톤, 이미지 비율, 선택 문구를 광고 생성 API payload로 묶는다. |
| `ui/ad_content.py` | `generate_copy_experiment()` | 여러 문구 provider 후보를 생성하고 첫 번째 성공 후보를 기본 선택값으로 반영한다. |
| `ui/ad_content.py` | `generate_poster()` | 광고 문구와 선택 템플릿으로 SVG 포스터를 생성한다. `include_completed_image=False`이면 완료된 이미지 job이 있어도 이미지 없이 포스터를 만든다. |
| `ui/ad_content.py` | `generate_image_job()` | 이미지 작업을 생성하고 job 상태를 반환한다. 문구 엔진과 이미지 backend를 분리하기 위해 이미지 작업은 OpenAI backend를 우선 사용한다. |
| `ui/ad_content.py` | `refresh_image_job()` | 진행 중인 이미지 job 상태를 다시 조회하고 polling 상태를 갱신한다. |
| `ui/ad_content.py` | `render_compact_copy_candidates()` | 광고 문구 후보를 오른쪽 패널 상단에 작게 보여주고 바로 선택할 수 있게 한다. |
| `ui/ad_content.py` | `render_ad_card_preview_section()` | 광고 카드 미리보기, 문구 후보, 선택 문구 편집 영역을 렌더링한다. |
| `ui/result_panel.py` | `_render_ad_preview()` | Step 4의 왼쪽 광고 결과 미리보기 영역을 렌더링한다. |
| `ui/result_panel.py` | `_render_step_content()` | 현재 단계에 맞춰 결과 영역과 편집 패널의 좌우 배치를 결정한다. |
