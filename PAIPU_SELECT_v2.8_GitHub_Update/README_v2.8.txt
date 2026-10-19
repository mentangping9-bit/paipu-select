PAIPU SELECT v2.8 로그인 요청 최소 수정본

적용: 압축 해제 후 PAIPU_SELECT_Mobile_Web_FullStack_v2 폴더를 GitHub 저장소의 최상위에 업로드하면
기존 파일인 server.py 및 regional_auth.py가 같은 경로에서 업데이트됩니다.
(다른 파일을 삭제하면 안 됩니다.)
Render 배포 후 /api/health 의 version 2.8 확인.

변경:
- 최신 Soulless 0.3.2 국제 서버 Yostar SDK와 동일하게
  /yostar/send-code 의 Account만 전송,
  /user/login 은 Type, OpenID, Token, Secret, CheckAccountPlus:0 필드를 전송.
- v2.7 최초 로그인에서 발급된 세션을 직접 쓰는 로직 및 이후 재로그인 경로 유지.
- server.py /api/health 버전 2.8.

검증:
- 오프라인 SDK 요청 본문 및 KR/JP/EN 지역 식별자/세션 테스트 통과.
- Python 구문 검사 통과.
- 실제 작혼 OAuth 110 해소 및 NAGA 제출 성공은 검증되지 않았음.

안전: 테스트에는 임의 토큰만 사용하며 Yostar 이메일 인증번호/토큰을 출력하지 않습니다.
