# PAIPU SELECT — 작혼 패보 → 국 선택 → NAGA

모바일 웹 / PC 웹 모두 지원. 크롬 확장프로그램이 필요하지 않습니다.

## 사용 흐름

1. 작혼 공유 패보 링크 입력 (`https://game.mahjongsoul.com/?paipu=...`).
2. Yostar 이메일 인증. 인증된 동안 같은 브라우저에서 반복 입력할 필요 없습니다 (메모리 세션 2시간).
3. 작혼 패보를 서버에서 조회해 Tenhou/6 JSON으로 변환합니다.
4. 동1국~남4국, 연장 본장을 체크해 선택합니다.
5. 한 국당 하나의 `https://tenhou.net/5/#json=...` 주소를 복사하고 NAGA 커스텀 패보 제출창에 붙여넣습니다. 최종 분석 신청/NP 사용은 사용자가 결정합니다.

## 배포 (Render)

1. 이 폴더의 **파일들**을 GitHub 저장소 루트에 올립니다.
2. Render → New → Blueprint에서 저장소 선택 (`render.yaml` 포함).
3. Render 배포 완료 후 `https://....onrender.com`으로 접속합니다.
4. Render의 Environment에서 `PUBLIC_HTTPS=1`이 있는지 확인합니다. 실제 공개 웹 주소는 사용자 배포 계정에서 발급됩니다.

`render.yaml`은 의존성 설치와 서버 시작 설정을 포함합니다. Render 무료 플랜은 유휴 중 중단될 수 있고 재시작하면 로그인 세션이 사라집니다.

로컬 실행 (Python 3.12 권장):

```bash
python -m pip install -r requirements.txt
python -m pip install --no-deps 'git+https://github.com/LekangZou/Mahjong-Replay-Converter.git@main'
python server.py
# http://localhost:8765
```

## API

- `POST /api/auth/send-code`: `{ "email": "..." }` Yostar 공식 인증코드 발송
- `POST /api/auth/verify`: `{ "code": "..." }` 인증코드 교환, HttpOnly 로그인 쿠키 발급
- `GET /api/auth/status`: `{ "authenticated": bool, "email": "..." }`
- `POST /api/auth/logout`: `{}` 서버 세션 종료
- `POST /api/convert`: `{ "url": "https://game.mahjongsoul.com/?paipu=..." }` Tenhou JSON 응답
- `GET /api/health`: 서버 상태

Yostar의 이메일 일회용 코드는 서비스에 보내지만 **로그에 남기지 않습니다**. 로그인된 토큰은 서버 메모리에만 두며 `HttpOnly` 세션 쿠키만 브라우저에 전달합니다. 외부 저장소, 사용자 브라우저 localStorage, 공유 URL에 인증 토큰을 넣지 않습니다. 사이트 운영자는 서버에서 세션 토큰을 보유할 수 있으므로 신뢰할 수 있는 운영자 계정에만 이메일 인증을 사용하세요. 서비스의 사칭이나 공식 제휴를 주장하지 마세요.

## 테스트

```bash
node tests/check.js
python -m unittest discover -s tests -p 'test_*.py' -v
```

`tests/test_site.py`는 로그인·패보 조회를 **모의 응답**으로 확인합니다. 본 실행 환경에는 외부 게임 서버 연결과 Yostar 인증 계정이 없어, 실제 게임 서버에서 패보 다운로드 및 NAGA 유료 접수 테스트는 이 저장소에서 자동 검증하지 않습니다. 배포 후 본인 계정으로 실제 테스트해야 합니다.

## 제약 및 출처

- 4인 마작 전용 (3인·특수 룰은 지원하지 않음)
- 한국/일본/미국 작혼의 Yostar 인증 방식 적용. 중국 서버는 별도의 인증 방식이므로 현재 링크 입력에서 거부합니다.
- 서버의 패보 다운로드·변환은 [LekangZou/Mahjong-Replay-Converter](https://github.com/LekangZou/Mahjong-Replay-Converter) (MIT) 라이브러리 사용. 이 라이브러리는 작혼 프로토콜이 바뀌면 수정이 필요할 수 있습니다.
- NAGA측 규격·NP 정책은 바뀔 수 있으며 본 사이트는 NAGA에 분석 신청을 자동 실행하지 않습니다.
- Mahjong Soul, NAGA, Tenhou와 제휴한 공식 서비스가 아닙니다.
