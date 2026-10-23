/* Text-only UI localization; replay JSON, tokens and account region are never changed. */
(() => {
'use strict';
const messages = {
  "아이폰에서 한 줄로 붙여넣어지나요?": {"ko":"아이폰에서 한 줄로 붙여넣어지나요?","en":"Pasting as one line on iPhone?","ja":"iPhoneで1行にまとまってしまいますか？"},
  "TXT 화면에서 전체 선택·복사한 뒤, 아래 링크로 NAGA를 열어 붙여넣어 주세요. 필요한 경우 URL TXT 저장도 사용할 수 있습니다.": {"ko":"TXT 화면에서 전체 선택·복사한 뒤, 아래 링크로 NAGA를 열어 붙여넣어 주세요. 필요한 경우 URL TXT 저장도 사용할 수 있습니다.","en":"Select all and copy in the TXT view, then use the link below to open NAGA and paste. You can also save the URL TXT file if needed.","ja":"TXT表示で全選択・コピーした後、下のリンクでNAGAを開いて貼り付けてください。必要に応じて「URL TXTを保存」も利用できます。"},
  "복사 없이 NAGA 열기 ↗": {"ko":"복사 없이 NAGA 열기 ↗","en":"Open NAGA without copying ↗","ja":"コピーせずNAGAを開く ↗"},
  "TXT 화면 열기 ↗": {"ko":"TXT 화면 열기 ↗","en":"Open TXT view ↗","ja":"TXT表示を開く ↗"},
  "복사한 줄바꿈 확인": {"ko":"복사한 줄바꿈 확인","en":"Check copied line breaks","ja":"コピー後の改行を確認"},
  "URL을 복사한 뒤 아래 칸에 붙여넣으세요. 확인 내용은 외부로 전송되지 않습니다.": {"ko":"URL을 복사한 뒤 아래 칸에 붙여넣으세요. 확인 내용은 외부로 전송되지 않습니다.","en":"Copy the URLs and paste them below. This check stays in your browser.","ja":"URLをコピーして下の欄に貼り付けてください。確認内容は外部に送信されません。"},
  "복사 확인용 붙여넣기": {"ko":"복사 확인용 붙여넣기","en":"Paste to check copying","ja":"コピー確認用の貼り付け欄"},
  "원문과 일치합니다. {n}개 URL의 줄바꿈이 유지됐습니다.": {"ko":"원문과 일치합니다. {n}개 URL의 줄바꿈이 유지됐습니다.","en":"Matches the original. Line breaks for all {n} URLs are preserved.","ja":"元の内容と一致しました。{n}個のURLの改行が維持されています。"},
  "줄바꿈이 사라졌습니다. 원본 {n}줄, 붙여넣기 {m}줄입니다.": {"ko":"줄바꿈이 사라졌습니다. 원본 {n}줄, 붙여넣기 {m}줄입니다.","en":"Line breaks were lost: {n} original lines, {m} pasted lines.","ja":"改行が失われています。元は{n}行、貼り付け後は{m}行です。"},
  "복사한 내용이 원문과 다릅니다. 원본 {n}줄, 붙여넣기 {m}줄입니다.": {"ko":"복사한 내용이 원문과 다릅니다. 원본 {n}줄, 붙여넣기 {m}줄입니다.","en":"The pasted content differs: {n} original lines, {m} pasted lines.","ja":"貼り付けた内容が元と異なります。元は{n}行、貼り付け後は{m}行です。"},
  "작혼 공유 링크를 NAGA 분석용 패보로 변환하고 원하는 국만 선택하세요. PC와 모바일에서 이용할 수 있습니다.": {"ko": "작혼 공유 링크를 NAGA 분석용 패보로 변환하고 원하는 국만 선택하세요. PC와 모바일에서 이용할 수 있습니다.", "en": "Convert a Mahjong Soul share link for NAGA analysis and select the rounds you want. Works on desktop and mobile.", "ja": "雀魂の共有リンクをNAGA解析用の牌譜に変換し、解析したい局だけを選べます。PC・スマートフォンに対応。"},
  "작혼 패보 → NAGA 분석용 변환": {"ko": "작혼 패보 → NAGA 분석용 변환", "en": "Mahjong Soul → NAGA replay converter", "ja": "雀魂牌譜 → NAGA解析用に変換"},
  "작혼 패보를 NAGA에서 분석할 수 있는 링크로 변환합니다.": {"ko": "작혼 패보를 NAGA에서 분석할 수 있는 링크로 변환합니다.", "en": "Convert Mahjong Soul replays into links you can submit to NAGA for analysis.", "ja": "雀魂の牌譜を、NAGAで解析できるリンクに変換します。"},
  "사용 순서": {"ko": "사용 순서", "en": "How to use", "ja": "使い方"},
  "작혼 공유 링크 붙여넣기": {"ko": "작혼 공유 링크 붙여넣기", "en": "Paste a Mahjong Soul share link", "ja": "雀魂の共有リンクを貼り付ける"},
  "작혼 패보의 공유 문구를 그대로 넣고 불러오세요.": {"ko": "작혼 패보의 공유 문구를 그대로 넣고 불러오세요.", "en": "Paste the full Mahjong Soul replay share text, then select Import.", "ja": "雀魂の牌譜共有テキストをそのまま貼り付け、読み込んでください。"},
  "동국·남국과 본장을 구분해 원하는 국만 체크하세요.": {"ko": "동국·남국과 본장을 구분해 원하는 국만 체크하세요.", "en": "Select the East or South rounds and honba you want to analyze.", "ja": "東場・南場、本場を確認して、解析したい局だけを選んでください。"},
  "NAGA에 URL 제출": {"ko": "NAGA에 URL 제출", "en": "Submit the URLs to NAGA", "ja": "NAGAにURLを提出する"},
  "생성한 URL을 복사해 NAGA 제출창에 붙여넣으세요.": {"ko": "생성한 URL을 복사해 NAGA 제출창에 붙여넣으세요.", "en": "Copy the generated URLs and paste them into the NAGA submission form.", "ja": "生成されたURLをコピーし、NAGAの解析申請画面に貼り付けてください。"},
  "최종 분석 신청과 NP 소모량 확인은 NAGA에서 직접 진행합니다.": {"ko": "최종 분석 신청과 NP 소모량 확인은 NAGA에서 직접 진행합니다.", "en": "Check the NP cost and submit the final analysis request on NAGA.", "ja": "NP消費量の確認と最終的な解析申請は、NAGAで行ってください。"},

  "대기 {waiting}건 · 처리 중 {processing}건": {"ko": "대기 {waiting}건 · 처리 중 {processing}건", "en": "Waiting: {waiting} · Processing: {processing}", "ja": "待機中：{waiting}件・処理中：{processing}件"},
  "연결되지 않는 조회 계정을 건너뛰고 다른 계정으로 다시 시도합니다.": {"ko": "연결되지 않는 조회 계정을 건너뛰고 다른 계정으로 다시 시도합니다.", "en": "Skipping an unavailable replay account and retrying with another account.", "ja": "接続できない取得用アカウントをスキップし、別のアカウントで再試行します。"},

  "작혼 패보 불러오기": {"ko": "작혼 패보 불러오기", "en": "Import replay", "ja": "雀魂牌譜を読み込む"},
  "작혼 링크": {"ko": "작혼 링크", "en": "Replay link", "ja": "雀魂リンク"},
  "불러오기": {"ko": "불러오기", "en": "Import", "ja": "読み込む"},
  "국": {"ko": "국", "en": "Round", "ja": "局"},
  "결과 · 점수": {"ko": "결과 · 점수", "en": "Result · points", "ja": "結果・点数"},
  "동": {"ko": "동", "en": "E", "ja": "東"},
  "남": {"ko": "남", "en": "S", "ja": "南"},
  "서": {"ko": "서", "en": "W", "ja": "西"},
  "북": {"ko": "북", "en": "N", "ja": "北"},
  "한국어·日本語·English로 복사한 작혼 패보 공유 문구 전체를 그대로 붙여넣어도 됩니다.": {"ko": "한국어·日本語·English로 복사한 작혼 패보 공유 문구 전체를 그대로 붙여넣어도 됩니다.", "en": "Paste the entire Mahjong Soul share text in Korean, Japanese or English.", "ja": "韓国語・日本語・英語の雀魂牌譜共有テキストをそのまま貼り付けられます。"},
  "작혼, 천봉, NAGA와 제휴하지 않았습니다. JSON 파일은 브라우저에서만 처리됩니다. 작혼 링크 조회에는 변환 서버를 이용합니다.": {"ko": "작혼, 천봉, NAGA와 제휴하지 않았습니다. JSON 파일은 브라우저에서만 처리됩니다. 작혼 링크 조회에는 변환 서버를 이용합니다.", "en": "Not affiliated with Mahjong Soul, Tenhou or NAGA. JSON files stay in your browser. Replay links are fetched through the conversion server.", "ja": "雀魂・天鳳・NAGAとは提携していません。JSONファイルはブラウザー内で処理され、雀魂リンクの取得には変換サーバーを使用します。"},
  "변환 서버를 준비하고 있습니다. 링크를 붙여넣거나 JSON 파일을 먼저 사용할 수 있습니다.": {"ko":"변환 서버를 준비하고 있습니다. 링크를 붙여넣거나 JSON 파일을 먼저 사용할 수 있습니다.","en":"Starting the conversion server. You can paste a link or use a JSON file now.","ja":"変換サーバーを起動中です。リンクの貼り付けやJSONファイルの読み込みは先に行えます。"},
  "서버 준비에 시간이 걸립니다. 잠시 후 다시 시도해 주세요.": {"ko":"서버 준비에 시간이 걸립니다. 잠시 후 다시 시도해 주세요.","en":"The server is taking longer to start. Please try again shortly.","ja":"サーバーの起動に時間がかかっています。しばらくしてから再試行してください。"},
  "패보 처리 중": {"ko": "패보 처리 중", "en": "Processing replay", "ja": "牌譜を処理中"},
  "대기열 {n}번째": {"ko": "대기열 {n}번째", "en": "Queue position: {n}", "ja": "順番待ち：{n}番目"},
  "작혼 패보를 가져와 변환하고 있습니다.": {"ko": "작혼 패보를 가져와 변환하고 있습니다.", "en": "Fetching and converting your Mahjong Soul replay.", "ja": "雀魂の牌譜を取得・変換しています。"},
  "작혼 조회 제한으로 잠시 쉬는 중입니다. 접수된 순서대로 자동 처리합니다.": {"ko": "작혼 조회 제한으로 잠시 쉬는 중입니다. 접수된 순서대로 자동 처리합니다.", "en": "Pausing for Mahjong Soul’s retrieval limit. Requests resume automatically in order.", "ja": "雀魂の取得制限のため一時休止中です。受付順に自動で処理を再開します。"},
  "전체 분당 10회로 순서대로 처리합니다. 다시 누르지 않아도 됩니다.": {"ko": "전체 분당 10회로 순서대로 처리합니다. 다시 누르지 않아도 됩니다.", "en": "Requests are processed in order, up to 10 per minute across all visitors. No need to submit again.", "ja": "全体で毎分10件まで、受付順に処理します。再送信は不要です。"},
  "조회 간격 대기: {n}초 이상": {"ko": "조회 간격 대기: {n}초 이상", "en": "Retrieval interval wait: at least {n} seconds", "ja": "取得間隔の待ち時間：あと{n}秒以上"},
  "대기 시간이 길어졌습니다. 잠시 후 다시 접수해 주세요.": {"ko": "대기 시간이 길어졌습니다. 잠시 후 다시 접수해 주세요.", "en": "The wait is taking longer than expected. Please submit again later.", "ja": "待ち時間が長くなっています。しばらくしてから再度お申し込みください。"},
  "서버 응답을 기다리는 중 연결이 끊겼습니다. 잠시 후 다시 접수해 주세요.": {"ko": "서버 응답을 기다리는 중 연결이 끊겼습니다. 잠시 후 다시 접수해 주세요.", "en": "The connection timed out. Please submit again shortly.", "ja": "サーバーへの接続がタイムアウトしました。しばらくしてから再度お試しください。"},
  "작혼의 패보 조회 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.": {"ko": "작혼의 패보 조회 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.", "en": "Mahjong Soul’s replay retrieval limit was reached. Please try again later.", "ja": "雀魂の牌譜取得制限に達しました。しばらくしてからお試しください。"},
  "대기 요청이 만료되었거나 서버가 재시작됐습니다. 다시 접수해 주세요.": {"ko": "대기 요청이 만료되었거나 서버가 재시작됐습니다. 다시 접수해 주세요.", "en": "Your queued request expired or the server restarted. Please submit again.", "ja": "待機中のリクエストが期限切れになったか、サーバーが再起動しました。再度お申し込みください。"},
  "대기열이 가득 찼습니다. 잠시 후 다시 접수해 주세요.": {"ko": "대기열이 가득 찼습니다. 잠시 후 다시 접수해 주세요.", "en": "The queue is full. Please submit again shortly.", "ja": "待機列が満員です。しばらくしてから再度お申し込みください。"},
  "이미 접수한 패보를 처리 중입니다. 완료 후 다른 패보를 접수해 주세요.": {"ko": "이미 접수한 패보를 처리 중입니다. 완료 후 다른 패보를 접수해 주세요.", "en": "Your previous replay is still queued or processing. Please wait before submitting another.", "ja": "受付済みの牌譜を処理中です。完了してから別の牌譜をお申し込みください。"},
  "등록할 조회 계정": {"ko": "등록할 조회 계정", "en": "Replay account to register", "ja": "登録する取得用アカウント"},
  "조회 계정 {n}": {"ko": "조회 계정 {n}", "en": "Replay account {n}", "ja": "取得用アカウント{n}"},
  "연결됨": {"ko": "연결됨", "en": "Connected", "ja": "接続済み"},
  "최초 인증 필요": {"ko": "최초 인증 필요", "en": "Initial authentication needed", "ja": "初回認証が必要"},
  "일시 휴식 중": {"ko": "일시 휴식 중", "en": "Temporarily paused", "ja": "一時休止中"},
  "PAIPU SELECT 홈": {"ko": "PAIPU SELECT 홈", "en": "PAIPU SELECT home", "ja": "PAIPU SELECT ホーム"},
  "조회 계정 상태 확인": {"ko": "조회 계정 상태 확인", "en": "Check replay accounts", "ja": "取得用アカウントの状態を確認"},
  "없음": {"ko": "없음", "en": "None", "ja": "なし"},
  "현재 처리 계정: {email}": {"ko": "현재 처리 계정: {email}", "en": "Processing account: {email}", "ja": "現在の処理アカウント：{email}"},
  "최근 조회 계정: {email}": {"ko": "최근 조회 계정: {email}", "en": "Last used account: {email}", "ja": "直前の取得アカウント：{email}"},
  "최근 성공 계정: {email}": {"ko": "최근 성공 계정: {email}", "en": "Last successful account: {email}", "ja": "直近の取得成功アカウント：{email}"},
  "다음 조회 계정: {email}": {"ko": "다음 조회 계정: {email}", "en": "Next account: {email}", "ja": "次の取得アカウント：{email}"},
  "게임 로그인 확인 필요": {"ko": "게임 로그인 확인 필요", "en": "Game login needs attention", "ja": "ゲームログインの確認が必要"},
  "휴식 {n}초": {"ko": "휴식 {n}초", "en": "Paused for {n} seconds", "ja": "あと{n}秒休止"},
  "조회 제한(540) 이력 · 재시도 가능": {"ko": "조회 제한(540) 이력 · 재시도 가능", "en": "Past retrieval limit (540) · eligible to retry", "ja": "取得制限(540)の履歴 · 再試行可能"},
  "패보 조회 성공 확인": {"ko": "패보 조회 성공 확인", "en": "Replay retrieval verified", "ja": "牌譜取得成功を確認済み"},
  "인증 완료 · 조회 확인 전": {"ko": "인증 완료 · 조회 확인 전", "en": "Authenticated; retrieval not yet verified", "ja": "認証済み・取得は未確認"},
  "조회 계정 {n}에서 패보를 가져와 변환하고 있습니다.": {"ko": "조회 계정 {n}에서 패보를 가져와 변환하고 있습니다.", "en": "Fetching and converting with replay account {n}.", "ja": "取得用アカウント{n}で牌譜を取得・変換しています。"},
  "Yostar 인증 서비스의 프로젝트 설정이 올바르지 않습니다. 운영자 점검이 필요합니다.": {"ko": "Yostar 인증 서비스의 프로젝트 설정이 올바르지 않습니다. 운영자 점검이 필요합니다.", "en": "The server’s Yostar project configuration is invalid. The operator needs to fix it.", "ja": "サーバーのYostarプロジェクト設定が正しくありません。運営者による修正が必要です。"},
  "패보 셀렉터 · 작혼 → NAGA": {
    "ko": "패보 셀렉터 · 작혼 → NAGA",
    "en": "PAIPU SELECT · Mahjong Soul → NAGA",
    "ja": "PAIPU SELECT · 雀魂 → NAGA"
  },
  "필요한 국만 골라서,": {
    "ko": "필요한 국만 골라서,",
    "en": "Choose your rounds.",
    "ja": "必要な局だけ選んで、"
  },
  "NAGA로.": {
    "ko": "NAGA로.",
    "en": "Send to NAGA.",
    "ja": "NAGAへ。"
  },
  "작혼 패보를 불러오고 분석할 동국·남국을 선택하세요.": {
    "ko": "작혼 패보를 불러오고 분석할 동국·남국을 선택하세요.",
    "en": "Import a Mahjong Soul replay and choose the rounds to analyze.",
    "ja": "雀魂の牌譜を読み込み、解析したい東場・南場の局を選択してください。"
  },
  "PC와 모바일에서 똑같이 사용할 수 있어요.": {
    "ko": "PC와 모바일에서 똑같이 사용할 수 있어요.",
    "en": "Works on desktop and mobile.",
    "ja": "PCでもスマートフォンでも使えます。"
  },
  "패보 불러오기": {
    "ko": "패보 불러오기",
    "en": "Import replay",
    "ja": "牌譜を読み込む"
  },
  "분석할 국 선택": {
    "ko": "분석할 국 선택",
    "en": "Choose rounds",
    "ja": "解析する局を選択"
  },
  "NAGA로 전달": {
    "ko": "NAGA로 전달",
    "en": "Send to NAGA",
    "ja": "NAGAへ送る"
  },
  "4인 마작 전용": {
    "ko": "4인 마작 전용",
    "en": "4-player only",
    "ja": "四人麻雀専用"
  },
  "작혼 패보 링크": {
    "ko": "작혼 패보 링크",
    "en": "Mahjong Soul link",
    "ja": "雀魂の牌譜リンク"
  },
  "JSON 파일": {
    "ko": "JSON 파일",
    "en": "JSON file",
    "ja": "JSONファイル"
  },
  "작혼 공유 URL": {
    "ko": "작혼 공유 URL",
    "en": "Mahjong Soul share URL",
    "ja": "雀魂の共有URL"
  },
  "한국어·日本語·English로 복사한 작혼 패보 공유 문구 전체를 그대로 붙여넣어도 됩니다. Yostar 인증은 최초 1회 또는 세션 만료 시 진행합니다.": {
    "ko": "한국어·日本語·English로 복사한 작혼 패보 공유 문구 전체를 그대로 붙여넣어도 됩니다. Yostar 인증은 최초 1회 또는 세션 만료 시 진행합니다.",
    "en": "Paste the full Korean, Japanese or English share text. The operator authenticates once, then again only if the session expires.",
    "ja": "韓国語・日本語・英語の共有文をそのまま貼り付けられます。運営者による認証は初回とセッション失効時に行います。"
  },
  "공용 패보 조회 계정 연결됨": {
    "ko": "공용 패보 조회 계정 연결됨",
    "en": "Replay service connected",
    "ja": "牌譜取得用アカウント接続済み"
  },
  "로그인 없이 작혼 공유 링크를 넣어 주세요.": {
    "ko": "로그인 없이 작혼 공유 링크를 넣어 주세요.",
    "en": "Paste a Mahjong Soul share link. No login needed.",
    "ja": "ログインせずに雀魂の共有リンクを入力できます。"
  },
  "운영자 인증 설정": {
    "ko": "운영자 인증 설정",
    "en": "Operator authentication",
    "ja": "運営者の認証設定"
  },
  "공용 조회 계정 설정": {
    "ko": "공용 조회 계정 설정",
    "en": "Replay service setup",
    "ja": "牌譜取得用アカウントの設定"
  },
  "Yostar 계정 인증": {
    "ko": "Yostar 계정 인증",
    "en": "Yostar authentication",
    "ja": "Yostarアカウント認証"
  },
  "작혼 패보를 읽기 위한 이메일 인증": {
    "ko": "작혼 패보를 읽기 위한 이메일 인증",
    "en": "Email authentication for replay access",
    "ja": "牌譜を取得するためのメール認証"
  },
  "내 Yostar 계정의 인증 지역": {
    "ko": "내 Yostar 계정의 인증 지역",
    "en": "Yostar account region",
    "ja": "Yostarアカウントの地域"
  },
  "한국 (KR) · 한섭": {
    "ko": "한국 (KR) · 한섭",
    "en": "Korea (KR)",
    "ja": "韓国（KR）"
  },
  "일본 (JP) · 일섭": {
    "ko": "일본 (JP) · 일섭",
    "en": "Japan (JP)",
    "ja": "日本（JP）"
  },
  "글로벌 영어 (US/EN)": {
    "ko": "글로벌 영어 (US/EN)",
    "en": "Global English (US/EN)",
    "ja": "グローバル英語（US/EN）"
  },
  "Yostar 로그인 이메일": {
    "ko": "Yostar 로그인 이메일",
    "en": "Yostar email address",
    "ja": "Yostarログインメールアドレス"
  },
  "인증 메일 발송": {
    "ko": "인증 메일 발송",
    "en": "Send verification email",
    "ja": "認証メールを送信"
  },
  "이메일로 받은 인증코드": {
    "ko": "이메일로 받은 인증코드",
    "en": "Email verification code",
    "ja": "メールで届いた認証コード"
  },
  "인증코드": {
    "ko": "인증코드",
    "en": "Verification code",
    "ja": "認証コード"
  },
  "로그인": {
    "ko": "로그인",
    "en": "Sign in",
    "ja": "ログイン"
  },
  "로그아웃": {
    "ko": "로그아웃",
    "en": "Sign out",
    "ja": "ログアウト"
  },
  "Yostar 공식 인증 메일을 사용합니다. 비밀번호는 요구하지 않으며 개인 로그인 세션은 서버 메모리에서 2시간 유지됩니다.": {
    "ko": "Yostar 공식 인증 메일을 사용합니다. 비밀번호는 요구하지 않으며 개인 로그인 세션은 서버 메모리에서 2시간 유지됩니다.",
    "en": "Uses official Yostar email verification. No password is requested. Personal sessions stay in server memory for two hours.",
    "ja": "Yostar公式のメール認証を使用します。パスワードは不要です。個人のログインセッションはサーバーのメモリに2時間保持されます。"
  },
  "패보 자동 변환하고 국 선택하기": {
    "ko": "패보 자동 변환하고 국 선택하기",
    "en": "Convert replay and choose rounds",
    "ja": "牌譜を変換して局を選択"
  },
  "연결 오류": {
    "ko": "연결 오류",
    "en": "Connection error",
    "ja": "接続エラー"
  },
  "JSON 파일 선택": {
    "ko": "JSON 파일 선택",
    "en": "Choose JSON file",
    "ja": "JSONファイルを選択"
  },
  "파일을 누르거나 이곳에 끌어 놓으세요": {
    "ko": "파일을 누르거나 이곳에 끌어 놓으세요",
    "en": "Choose a file or drag it here",
    "ja": "ファイルを選ぶか、ここにドラッグしてください"
  },
  ".json / .txt / 천봉 URL 목록": {
    "ko": ".json / .txt / 천봉 URL 목록",
    "en": ".json / .txt / Tenhou URL list",
    "ja": ".json / .txt / 天鳳URLリスト"
  },
  "빅코치에서 받은 JSON 또는 천봉 형식의 JSON이 지원됩니다. 업로드한 파일은 외부로 전송되지 않습니다.": {
    "ko": "빅코치에서 받은 JSON 또는 천봉 형식의 JSON이 지원됩니다. 업로드한 파일은 외부로 전송되지 않습니다.",
    "en": "Supports BigCoach exports and Tenhou JSON. Files are processed in your browser and are not uploaded.",
    "ja": "BigCoach出力と天鳳形式のJSONに対応しています。ファイルはブラウザ内で処理され、外部には送信されません。"
  },
  "다른 패보 ↗": {
    "ko": "다른 패보 ↗",
    "en": "Another replay ↗",
    "ja": "別の牌譜 ↗"
  },
  "불러온 패보": {
    "ko": "불러온 패보",
    "en": "Imported replay",
    "ja": "読み込んだ牌譜"
  },
  "국": {
    "ko": "국",
    "en": "rounds",
    "ja": "局"
  },
  "대국 목록": {
    "ko": "대국 목록",
    "en": "Rounds",
    "ja": "局一覧"
  },
  "체크한 국만 NAGA용 링크에 포함됩니다.": {
    "ko": "체크한 국만 NAGA용 링크에 포함됩니다.",
    "en": "Only selected rounds are included in the NAGA links.",
    "ja": "選択した局だけがNAGA用リンクに含まれます。"
  },
  "0국 선택": {
    "ko": "0국 선택",
    "en": "0 selected",
    "ja": "0局選択"
  },
  "전체": {
    "ko": "전체",
    "en": "All",
    "ja": "すべて"
  },
  "동국": {
    "ko": "동국",
    "en": "East",
    "ja": "東場"
  },
  "남국": {
    "ko": "남국",
    "en": "South",
    "ja": "南場"
  },
  "해제": {
    "ko": "해제",
    "en": "Clear",
    "ja": "解除"
  },
  "플레이어 닉네임 익명화": {
    "ko": "플레이어 닉네임 익명화",
    "en": "Anonymize player names",
    "ja": "プレイヤー名を匿名化"
  },
  "선택한 국": {
    "ko": "선택한 국",
    "en": "Selected rounds:",
    "ja": "選択した局："
  },
  "개": {
    "ko": "개",
    "en": "",
    "ja": "局"
  },
  "개 국의 URL 생성": {
    "ko": "개 국의 URL 생성",
    "en": "round URLs",
    "ja": "局分のURLを生成"
  },
  "NAGA용 패보 생성": {
    "ko": "NAGA용 패보 생성",
    "en": "Create NAGA replay URLs",
    "ja": "NAGA用牌譜を作成"
  },
  "NAGA 제출용 URL": {
    "ko": "NAGA 제출용 URL",
    "en": "URLs for NAGA",
    "ja": "NAGA提出用URL"
  },
  "국별 천봉 URL (한 줄당 한 국)": {
    "ko": "국별 천봉 URL (한 줄당 한 국)",
    "en": "Tenhou URLs (one round per line)",
    "ja": "局ごとの天鳳URL（1行につき1局）"
  },
  "복사하고 NAGA 열기 ↗": {
    "ko": "복사하고 NAGA 열기 ↗",
    "en": "Copy and open NAGA ↗",
    "ja": "コピーしてNAGAを開く ↗"
  },
  "URL만 복사": {
    "ko": "URL만 복사",
    "en": "Copy URLs",
    "ja": "URLをコピー"
  },
  "NAGA의 커스텀 패보 제출창에 복사한 내용을 붙여넣으세요. 최종 신청은 직접 진행하며 NP가 소모될 수 있습니다.": {
    "ko": "NAGA의 커스텀 패보 제출창에 복사한 내용을 붙여넣으세요. 최종 신청은 직접 진행하며 NP가 소모될 수 있습니다.",
    "en": "Paste into NAGA’s custom replay form. Submit the analysis yourself; NP may be charged.",
    "ja": "NAGAのカスタム牌譜提出欄に貼り付けてください。最終的な解析申請はご自身で行ってください。NPを消費する場合があります。"
  },
  "← 국 다시 선택": {
    "ko": "← 국 다시 선택",
    "en": "← Change selection",
    "ja": "← 局を選び直す"
  },
  "선택한 JSON 저장 ↓": {
    "ko": "선택한 JSON 저장 ↓",
    "en": "Save selected JSON ↓",
    "ja": "選択したJSONを保存 ↓"
  },
  "URL TXT 저장 ↓": {
    "ko": "URL TXT 저장 ↓",
    "en": "Save URL TXT ↓",
    "ja": "URLをTXTで保存 ↓"
  },
  "PAIPU SELECT · 비공식 팬 제작 도구": {
    "ko": "PAIPU SELECT · 비공식 팬 제작 도구",
    "en": "PAIPU SELECT · Unofficial fan tool",
    "ja": "PAIPU SELECT · 非公式ファンツール"
  },
  "작혼, 천봉, NAGA와 제휴하지 않았습니다. JSON 파일은 브라우저에서만 처리됩니다. 로그인 인증은 웹서버를 이용합니다.": {
    "ko": "작혼, 천봉, NAGA와 제휴하지 않았습니다. JSON 파일은 브라우저에서만 처리됩니다. 로그인 인증은 웹서버를 이용합니다.",
    "en": "Not affiliated with Mahjong Soul, Tenhou or NAGA. JSON files stay in your browser. Authentication uses the web server.",
    "ja": "雀魂・天鳳・NAGAとは提携していません。JSONファイルはブラウザ内でのみ処理され、ログイン認証にはWebサーバーを使用します。"
  },
  "작혼 공유 패보": {
    "ko": "작혼 공유 패보",
    "en": "Shared Mahjong Soul replay",
    "ja": "雀魂の共有牌譜"
  },
  "천봉 URL 패보": {
    "ko": "천봉 URL 패보",
    "en": "Tenhou URL replay",
    "ja": "天鳳URL牌譜"
  },
  "화료": {
    "ko": "화료",
    "en": "Win",
    "ja": "和了"
  },
  "유국": {
    "ko": "유국",
    "en": "Draw",
    "ja": "流局"
  },
  "종료 기록 불명": {
    "ko": "종료 기록 불명",
    "en": "Unknown ending",
    "ja": "終了記録不明"
  },
  "결과 미상": {
    "ko": "결과 미상",
    "en": "Unknown result",
    "ja": "結果不明"
  },
  " · 점수 정보 부족": {
    "ko": " · 점수 정보 부족",
    "en": " · Insufficient score data",
    "ja": "・点数情報不足"
  },
  "{n}국 선택": {
    "ko": "{n}국 선택",
    "en": "{n} selected",
    "ja": "{n}局選択"
  },
  "✓ 선택한 {n}개 국의 URL을 만들었습니다.": {
    "ko": "✓ 선택한 {n}개 국의 URL을 만들었습니다.",
    "en": "✓ Created URLs for {n} selected rounds.",
    "ja": "✓ 選択した{n}局のURLを作成しました。"
  },
  "{n}개 국의 타점을 원본 점수 증감에서 복원했습니다. 원본에 없는 부수·판수·역은 추가하지 않았습니다.": {
    "ko": "{n}개 국의 타점을 원본 점수 증감에서 복원했습니다. 원본에 없는 부수·판수·역은 추가하지 않았습니다.",
    "en": "Recovered points for {n} rounds from recorded score changes. No missing fu, han or yaku were invented.",
    "ja": "{n}局の打点を元の点数増減から復元しました。元データにない符・翻・役は追加していません。"
  },
  "{n}개 국은 원본의 점수 정보가 부족하거나 특수 정산을 확정할 수 없어 종료 기록을 '不明'으로 표기했습니다.": {
    "ko": "{n}개 국은 원본의 점수 정보가 부족하거나 특수 정산을 확정할 수 없어 종료 기록을 '不明'으로 표기했습니다.",
    "en": "{n} rounds have insufficient scoring data or ambiguous settlements; their endings are marked unknown (不明).",
    "ja": "{n}局は点数情報が不足しているか特殊な精算を確定できないため、終了記録を「不明」としました。"
  },
  "파일 크기는 10MB 이하여야 합니다.": {
    "ko": "파일 크기는 10MB 이하여야 합니다.",
    "en": "Files must be 10 MB or smaller.",
    "ja": "ファイルは10MB以下にしてください。"
  },
  "패보를 해석하지 못했습니다: ": {
    "ko": "패보를 해석하지 못했습니다: ",
    "en": "Could not parse replay: ",
    "ja": "牌譜を解析できませんでした："
  },
  "파일을 읽는 중 오류: ": {
    "ko": "파일을 읽는 중 오류: ",
    "en": "Could not read file: ",
    "ja": "ファイルの読み込みエラー："
  },
  "URL JSON을 읽을 수 없습니다: ": {
    "ko": "URL JSON을 읽을 수 없습니다: ",
    "en": "Could not read URL JSON: ",
    "ja": "URL内のJSONを読み込めません："
  },
  "서버가 올바른 JSON을 반환하지 않았습니다.": {
    "ko": "서버가 올바른 JSON을 반환하지 않았습니다.",
    "en": "The server did not return valid JSON.",
    "ja": "サーバーから正しいJSONが返されませんでした。"
  },
  "서버 응답에 천봉 JSON이 없습니다.": {
    "ko": "서버 응답에 천봉 JSON이 없습니다.",
    "en": "The response contains no Tenhou JSON.",
    "ja": "サーバー応答に天鳳JSONがありません。"
  },
  "대국 기록을 찾지 못했습니다.": {
    "ko": "대국 기록을 찾지 못했습니다.",
    "en": "No rounds found.",
    "ja": "対局記録が見つかりません。"
  },
  "작혼 패보를 가져오는 중…": {
    "ko": "작혼 패보를 가져오는 중…",
    "en": "Fetching replay…",
    "ja": "牌譜を取得中…"
  },
  "공용 계정 연결 상태를 확인해 주세요.": {
    "ko": "공용 계정 연결 상태를 확인해 주세요.",
    "en": "Check the replay service connection.",
    "ja": "牌譜取得用アカウントの接続状態を確認してください。"
  },
  "Yostar 이메일 인증이 필요합니다.": {
    "ko": "Yostar 이메일 인증이 필요합니다.",
    "en": "Yostar email authentication is required.",
    "ja": "Yostarのメール認証が必要です。"
  },
  "서버 오류 HTTP {n}": {
    "ko": "서버 오류 HTTP {n}",
    "en": "Server error HTTP {n}",
    "ja": "サーバーエラー HTTP {n}"
  },
  "110초 동안 서버 응답이 없습니다.": {
    "ko": "110초 동안 서버 응답이 없습니다.",
    "en": "No server response within 110 seconds.",
    "ja": "110秒以内にサーバーから応答がありませんでした。"
  },
  "변환 서버에 연결할 수 없습니다.": {
    "ko": "변환 서버에 연결할 수 없습니다.",
    "en": "Cannot connect to the conversion server.",
    "ja": "変換サーバーに接続できません。"
  },
  "NAGA용 URL을 복사했어요.": {
    "ko": "NAGA용 URL을 복사했어요.",
    "en": "Copied NAGA URLs.",
    "ja": "NAGA用URLをコピーしました。"
  },
  "URL을 복사했어요.": {
    "ko": "URL을 복사했어요.",
    "en": "Copied URLs.",
    "ja": "URLをコピーしました。"
  },
  "자동 복사가 허용되지 않았습니다. 선택된 URL을 직접 복사해 주세요.": {
    "ko": "자동 복사가 허용되지 않았습니다. 선택된 URL을 직접 복사해 주세요.",
    "en": "Automatic copy was blocked. Copy the selected URLs manually.",
    "ja": "自動コピーが許可されませんでした。選択されたURLを手動でコピーしてください。"
  },
  "공용 계정 인증 메일 발송": {
    "ko": "공용 계정 인증 메일 발송",
    "en": "Send service verification email",
    "ja": "共用アカウントの認証メールを送信"
  },
  " 인증 정보는 외부 DB에 암호화 저장되며 서버 재시작 후 복원됩니다.": {
    "ko": " 인증 정보는 외부 DB에 암호화 저장되며 서버 재시작 후 복원됩니다.",
    "en": " Credentials are encrypted in an external database and restored after server replacement.",
    "ja": " 認証情報は外部DBに暗号化して保存され、サーバー再起動後に復元されます。"
  },
  " 세션은 서버의 암호화 저장 파일에서 복원됩니다.": {
    "ko": " 세션은 서버의 암호화 저장 파일에서 복원됩니다.",
    "en": " The session is restored from an encrypted server file.",
    "ja": " セッションはサーバーの暗号化ファイルから復元されます。"
  },
  " 현재 메모리 저장 모드이므로 서버 재시작 후에는 운영자 재인증이 필요합니다.": {
    "ko": " 현재 메모리 저장 모드이므로 서버 재시작 후에는 운영자 재인증이 필요합니다.",
    "en": " Memory storage is active; the operator must sign in after a restart.",
    "ja": " 現在はメモリ保存のため、サーバー再起動後に運営者の再認証が必要です。"
  },
  "서버에 지정한 공용 계정 이메일로 인증하면 방문자가 로그인 없이 패보를 조회할 수 있습니다.": {
    "ko": "서버에 지정한 공용 계정 이메일로 인증하면 방문자가 로그인 없이 패보를 조회할 수 있습니다.",
    "en": "Verify the configured service email so visitors can fetch replays without signing in.",
    "ja": "サーバー指定の共用メールで認証すると、訪問者はログインせずに牌譜を取得できます。"
  },
  "공용 계정의 최초 인증 또는 재인증이 필요합니다. 운영자 설정 화면에서 연결해 주세요.": {
    "ko": "공용 계정의 최초 인증 또는 재인증이 필요합니다. 운영자 설정 화면에서 연결해 주세요.",
    "en": "The replay service needs initial verification or reauthentication. Use operator settings.",
    "ja": "共用アカウントの初回認証または再認証が必要です。運営者設定から接続してください。"
  },
  "인증 저장소에 연결할 수 없습니다. 인증 정보는 보존되어 있으며 서버의 저장소 설정 확인이 필요합니다. JSON 업로드는 계속 사용할 수 있습니다.": {
    "ko": "인증 저장소에 연결할 수 없습니다. 인증 정보는 보존되어 있으며 서버의 저장소 설정 확인이 필요합니다. JSON 업로드는 계속 사용할 수 있습니다.",
    "en": "Cannot connect to credential storage. Saved credentials are preserved. Check server settings; JSON import is still available.",
    "ja": "認証情報の保存先に接続できません。保存済みの情報は保持されています。サーバー設定を確認してください。JSON読み込みは引き続き利用できます。"
  },
  "지정된 공용 계정만 등록됩니다. 일반 방문자에게 이메일·토큰은 공개되지 않습니다. 인증이 만료되면 운영자가 다시 인증해야 합니다.": {
    "ko": "지정된 공용 계정만 등록됩니다. 일반 방문자에게 이메일·토큰은 공개되지 않습니다. 인증이 만료되면 운영자가 다시 인증해야 합니다.",
    "en": "Only the configured service account can be registered. Its email and tokens are not exposed to visitors. The operator must reauthenticate if the session expires.",
    "ja": "指定された共用アカウントのみ登録できます。訪問者にメールやトークンは公開されません。認証が失効した場合は運営者の再認証が必要です。"
  },
  "로그인됨": {
    "ko": "로그인됨",
    "en": "Signed in",
    "ja": "ログイン済み"
  },
  "공용 조회 계정 연결됨": {
    "ko": "공용 조회 계정 연결됨",
    "en": "Replay service connected",
    "ja": "牌譜取得用アカウント接続済み"
  },
  "공용 계정 최초 인증 필요": {
    "ko": "공용 계정 최초 인증 필요",
    "en": "Service verification required",
    "ja": "共用アカウントの初回認証が必要です"
  },
  "게임 로그인 및 패보 조회 확인됨": {
    "ko": "게임 로그인 및 패보 조회 확인됨",
    "en": "Game login and replay access verified",
    "ja": "ゲームへのログインと牌譜取得を確認済み"
  },
  "이메일 인증 완료 · 게임 로그인은 조회 시 확인": {
    "ko": "이메일 인증 완료 · 게임 로그인은 조회 시 확인",
    "en": "Email verified · Game login checked when fetching",
    "ja": "メール認証済み・牌譜取得時にゲームログインを確認"
  },
  "계정 연결 상태를 확인하지 못했습니다. 페이지를 새로고침해 주세요.": {
    "ko": "계정 연결 상태를 확인하지 못했습니다. 페이지를 새로고침해 주세요.",
    "en": "Could not check the account connection. Reload the page.",
    "ja": "アカウントの接続状態を確認できませんでした。ページを再読み込みしてください。"
  },
  "발송 중…": {
    "ko": "발송 중…",
    "en": "Sending…",
    "ja": "送信中…"
  },
  "Yostar 인증 메일을 확인해 주세요.": {
    "ko": "Yostar 인증 메일을 확인해 주세요.",
    "en": "Check your Yostar verification email.",
    "ja": "Yostarの認証メールを確認してください。"
  },
  "인증 중…": {
    "ko": "인증 중…",
    "en": "Verifying…",
    "ja": "認証中…"
  },
  "인증 성공.": {
    "ko": "인증 성공.",
    "en": "Authentication successful.",
    "ja": "認証に成功しました。"
  },
  "로그아웃했습니다.": {
    "ko": "로그아웃했습니다.",
    "en": "Signed out.",
    "ja": "ログアウトしました。"
  },
  "패보 변환 라이브러리 로딩에 실패했습니다. 서버 설치 상태를 확인해 주세요.": {
    "ko": "패보 변환 라이브러리 로딩에 실패했습니다. 서버 설치 상태를 확인해 주세요.",
    "en": "Replay converter failed to load. Check the server installation.",
    "ja": "牌譜変換ライブラリの読み込みに失敗しました。サーバーのインストール状態を確認してください。"
  },
  "패보 서버가 실행되고 있지 않습니다. 웹서버로 사이트를 열어야 합니다.": {
    "ko": "패보 서버가 실행되고 있지 않습니다. 웹서버로 사이트를 열어야 합니다.",
    "en": "The replay server is unavailable. Open the site through its web server.",
    "ja": "牌譜サーバーを利用できません。Webサーバー経由でサイトを開いてください。"
  },
  "작혼 공유 문구가 너무 길거나 올바르지 않습니다.": {
    "ko": "작혼 공유 문구가 너무 길거나 올바르지 않습니다.",
    "en": "The share text is too long or invalid.",
    "ja": "共有文が長すぎるか、正しくありません。"
  },
  "복사한 내용에서 공식 작혼 패보 링크를 찾지 못했습니다. 공유 문구 전체를 붙여넣어도 됩니다.": {
    "ko": "복사한 내용에서 공식 작혼 패보 링크를 찾지 못했습니다. 공유 문구 전체를 붙여넣어도 됩니다.",
    "en": "No official Mahjong Soul replay link found. You can paste the entire share text.",
    "ja": "公式の雀魂牌譜リンクが見つかりません。共有文全体を貼り付けられます。"
  },
  "천봉 URL에 #json= 데이터가 없습니다. 전적 ID 링크가 아닌 JSON 패보 URL이 필요합니다.": {
    "ko": "천봉 URL에 #json= 데이터가 없습니다. 전적 ID 링크가 아닌 JSON 패보 URL이 필요합니다.",
    "en": "The Tenhou URL has no #json= data. A JSON replay URL is required.",
    "ja": "天鳳URLに#json=データがありません。JSON形式の牌譜URLが必要です。"
  },
  "파일을 텍스트로 읽을 수 없습니다.": {
    "ko": "파일을 텍스트로 읽을 수 없습니다.",
    "en": "Cannot read the file as text.",
    "ja": "ファイルをテキストとして読み込めません。"
  },
  "10MB를 넘는 파일은 지원하지 않습니다.": {
    "ko": "10MB를 넘는 파일은 지원하지 않습니다.",
    "en": "Files over 10 MB are not supported.",
    "ja": "10MBを超えるファイルには対応していません。"
  },
  "파일 내용이 비어 있습니다.": {
    "ko": "파일 내용이 비어 있습니다.",
    "en": "The file is empty.",
    "ja": "ファイルが空です。"
  },
  "JSON이 아니거나 지원하는 천봉 URL 목록이 아닙니다.": {
    "ko": "JSON이 아니거나 지원하는 천봉 URL 목록이 아닙니다.",
    "en": "Not valid JSON or a supported Tenhou URL list.",
    "ja": "JSONまたは対応する天鳳URLリストではありません。"
  },
  "표준 천봉/6 패보의 log 배열을 찾지 못했습니다. 빅코치에서 내려받은 실제 JSON 샘플이 있으면 형식에 맞게 확장할 수 있습니다.": {
    "ko": "표준 천봉/6 패보의 log 배열을 찾지 못했습니다. 빅코치에서 내려받은 실제 JSON 샘플이 있으면 형식에 맞게 확장할 수 있습니다.",
    "en": "No standard Tenhou replay log found. Import Tenhou-compatible JSON.",
    "ja": "標準の天鳳形式のlog配列が見つかりません。天鳳互換のJSONを読み込んでください。"
  },
  "NAGA는 4인 마작 패보만 지원합니다.": {
    "ko": "NAGA는 4인 마작 패보만 지원합니다.",
    "en": "NAGA only supports 4-player replays.",
    "ja": "NAGAは四人麻雀の牌譜のみに対応しています。"
  },
  "NAGA는 3인 마작 패보를 분석하지 못합니다.": {
    "ko": "NAGA는 3인 마작 패보를 분석하지 못합니다.",
    "en": "NAGA cannot analyze 3-player replays.",
    "ja": "NAGAでは三人麻雀の牌譜を解析できません。"
  },
  "천봉 JSON URL이 아닙니다.": {
    "ko": "천봉 JSON URL이 아닙니다.",
    "en": "Not a Tenhou JSON URL.",
    "ja": "天鳳JSON形式のURLではありません。"
  },
  "요청에 실패했습니다. 잠시 후 다시 시도해 주세요.": {
    "ko": "요청에 실패했습니다. 잠시 후 다시 시도해 주세요.",
    "en": "Request failed. Please try again shortly.",
    "ja": "処理に失敗しました。しばらくしてから再度お試しください。"
  },
  "같은 계정의 패보를 조회하고 있습니다. 완료 후 다시 시도해 주세요.": {
    "ko": "같은 계정의 패보를 조회하고 있습니다. 완료 후 다시 시도해 주세요.",
    "en": "Another replay request is in progress. Try again after it finishes.",
    "ja": "別の牌譜を取得中です。完了後にもう一度お試しください。"
  },
  "패보 입력 방법": {
    "ko": "패보 입력 방법",
    "en": "Replay input method",
    "ja": "牌譜の入力方法"
  },
  "작혼 패보의 원하는 국만 골라 NAGA용 천봉 URL을 만드는 모바일 국 선택기": {
    "ko": "작혼 패보의 원하는 국만 골라 NAGA용 천봉 URL을 만드는 모바일 국 선택기",
    "en": "Choose Mahjong Soul replay rounds and create Tenhou JSON URLs for NAGA.",
    "ja": "雀魂の牌譜から必要な局を選び、NAGA用の天鳳JSON URLを作成します。"
  },
  "작혼 패보:https://mahjongsoul.game.yo-star.com/?paipu=...": {
    "ko": "작혼 패보:https://mahjongsoul.game.yo-star.com/?paipu=...",
    "en": "Mahjong Soul Replay: https://game.mahjongsoul.com/?paipu=...",
    "ja": "雀魂牌譜:https://game.mahjongsoul.com/?paipu=..."
  },
  "작혼 서버에서 해당 패보를 읽지 못했습니다.": {
    "ko": "작혼 서버에서 해당 패보를 읽지 못했습니다.",
    "en": "Could not retrieve this replay from Mahjong Soul.",
    "ja": "雀魂サーバーからこの牌譜を取得できませんでした。"
  },
  "작혼 서버 연결 또는 패보 응답 검증에 실패했습니다.": {
    "ko": "작혼 서버 연결 또는 패보 응답 검증에 실패했습니다.",
    "en": "Could not verify the game server connection or replay response.",
    "ja": "ゲームサーバーへの接続または牌譜応答の検証に失敗しました。"
  },
  "이 서버에서 패보를 찾지 못했습니다. 공유 링크와 서버 지역을 확인해 주세요.": {
    "ko": "이 서버에서 패보를 찾지 못했습니다. 공유 링크와 서버 지역을 확인해 주세요.",
    "en": "Replay not found. Check the share link and server region.",
    "ja": "牌譜が見つかりません。共有リンクとサーバー地域を確認してください。"
  },
  "작혼 서버 응답 시간 초과입니다. 잠시 후 다시 시도해 주세요.": {
    "ko": "작혼 서버 응답 시간 초과입니다. 잠시 후 다시 시도해 주세요.",
    "en": "Mahjong Soul timed out. Please try again shortly.",
    "ja": "雀魂サーバーの応答がタイムアウトしました。しばらくしてから再度お試しください。"
  },
  "Yostar가 저장된 세션의 자동 인증을 거부했습니다. 인증 정보는 보존했습니다. 잠시 후 다시 시도하고, 계속 실패하면 운영자 설정에서 이메일 재인증해 주세요.": {
    "ko": "Yostar가 저장된 세션의 자동 인증을 거부했습니다. 인증 정보는 보존했습니다. 잠시 후 다시 시도하고, 계속 실패하면 운영자 설정에서 이메일 재인증해 주세요.",
    "en": "Yostar rejected automatic authentication. Saved credentials are preserved. Retry shortly; if it persists, the operator must verify by email again.",
    "ja": "Yostarが自動認証を拒否しました。保存済みの認証情報は保持されています。再試行しても解決しない場合は、運営者設定でメール認証をやり直してください。"
  },
  "인증 세션이 만료됐습니다. Yostar 인증을 다시 진행해 주세요.": {
    "ko": "인증 세션이 만료됐습니다. Yostar 인증을 다시 진행해 주세요.",
    "en": "The session expired. Verify your Yostar email again.",
    "ja": "認証セッションが失効しました。Yostarの認証をやり直してください。"
  },
  "저장된 인증 세션을 사용할 수 없습니다. 이메일 인증을 다시 진행해 주세요.": {
    "ko": "저장된 인증 세션을 사용할 수 없습니다. 이메일 인증을 다시 진행해 주세요.",
    "en": "The saved session is unavailable. Email verification is required again.",
    "ja": "保存済みの認証セッションを使用できません。メール認証をやり直してください。"
  },
  "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.": {
    "ko": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
    "en": "Too many requests. Please try again shortly.",
    "ja": "リクエストが多すぎます。しばらくしてから再度お試しください。"
  },
  "운영자 인증키": {
    "ko": "운영자 인증키",
    "en": "Operator access key",
    "ja": "運営者認証キー"
  },
  "운영자만 계정 인증 설정을 변경할 수 있습니다. 인증키는 저장하지 않습니다.": {
    "ko": "운영자만 계정 인증 설정을 변경할 수 있습니다. 인증키는 저장하지 않습니다.",
    "en": "Only the operator can change account authentication. The access key is not saved.",
    "ja": "アカウント認証設定の変更は運営者のみ可能です。認証キーは保存しません。"
  },
  "공용 계정의 인증 설정에는 운영자 인증키가 필요합니다.": {
    "ko": "공용 계정의 인증 설정에는 운영자 인증키가 필요합니다.",
    "en": "An operator access key is required to manage service authentication.",
    "ja": "共用アカウントの認証設定には運営者認証キーが必要です。"
  },
  "150초 동안 서버 응답이 없습니다.": {
    "ko": "150초 동안 서버 응답이 없습니다.",
    "en": "No server response within 150 seconds.",
    "ja": "150秒以内にサーバーから応答がありませんでした。"
  },
  "{n}분": {
    "ko": "{n}분",
    "en": "{n} min",
    "ja": "{n}分"
  },
  "{n}초": {
    "ko": "{n}초",
    "en": "{n} sec",
    "ja": "{n}秒"
  },
  "{time} 후 다시 시도": {
    "ko": "{time} 후 다시 시도",
    "en": "Try again in {time}",
    "ja": "{time}後に再試行"
  },
  "현재 다른 패보를 처리 중입니다. 잠시 후 다시 시도해 주세요.": {
    "ko": "현재 다른 패보를 처리 중입니다. 잠시 후 다시 시도해 주세요.",
    "en": "Other replays are being processed. Please try again shortly.",
    "ja": "現在、他の牌譜を処理中です。しばらくしてから再度お試しください。"
  },
  "짧은 시간에 요청이 많았습니다. 버튼의 대기 시간이 끝나면 다시 이용할 수 있습니다.": {
    "ko": "짧은 시간에 요청이 많았습니다. 버튼의 대기 시간이 끝나면 다시 이용할 수 있습니다.",
    "en": "Too many requests in a short time. Try again when the button countdown finishes.",
    "ja": "短時間にリクエストが集中しました。ボタンの待ち時間が終わると再び利用できます。"
  },
  "현재 패보 조회가 몰리고 있습니다. 버튼의 대기 시간이 끝나면 다시 시도해 주세요.": {
    "ko": "현재 패보 조회가 몰리고 있습니다. 버튼의 대기 시간이 끝나면 다시 시도해 주세요.",
    "en": "Replay requests are unusually high. Try again when the button countdown finishes.",
    "ja": "現在、牌譜の取得が混み合っています。ボタンの待ち時間が終わってから再度お試しください。"
  }
};
const supported = ['ko','en','ja'];
let language = 'ko';
try { const saved=localStorage.getItem('paipu-language'); language=supported.includes(saved)?saved:(supported.find(v=>(navigator.language||'').toLowerCase().startsWith(v))||'ko'); } catch {}
const translate=(key, values={})=>String(messages[key]?.[language]??key).replace(/\{(\w+)\}/g,(_,k)=>String(values[k]??`{${k}}`));
const sources=[];
const walker=document.createTreeWalker(document.documentElement,NodeFilter.SHOW_TEXT);
while(walker.nextNode()){
 const node=walker.currentNode, source=node.nodeValue;
 if(['SCRIPT','STYLE'].includes(node.parentElement?.tagName))continue;
 const trimmed=source.trim();
 if(messages[trimmed])sources.push({node,key:trimmed,before:source.slice(0,source.indexOf(trimmed)),after:source.slice(source.indexOf(trimmed)+trimmed.length)});
}
const attributes=[];
for(const element of document.querySelectorAll('[placeholder],[aria-label],meta[name="description"]'))for(const attr of ['placeholder','aria-label','content']){
 const key=element.getAttribute(attr);if(messages[key])attributes.push({element,attr,key});
}
const apply=()=>{
 document.documentElement.lang=language;
 for(const {node,key,before,after} of sources)if(node.isConnected)node.nodeValue=before+translate(key)+after;
 for(const {element,attr,key} of attributes)element.setAttribute(attr,translate(key));
 document.getElementById('languageSelect').value=language;
};
function setLanguage(value){if(!supported.includes(value))return;language=value;try{localStorage.setItem('paipu-language',value);}catch{}apply();document.dispatchEvent(new Event('paipu-language-change'));}
const error=message=>{
 const text=String(message||'');
 if(messages[text]||language==='ko')return translate(text);
 if(text.startsWith('JSON 문법을 해석할 수 없습니다: '))return language==='ja'?'JSONの形式が正しくありません。':'Invalid JSON syntax.';
 return /[가-힣]/.test(text)?translate('요청에 실패했습니다. 잠시 후 다시 시도해 주세요.'):text;
};
const roundName=(no,honba=0)=>{
 const winds=language==='en'?['East','South','West','North']:language==='ja'?['東','南','西','北']:['동','남','서','북'];
 const base=language==='en'?`${winds[Math.floor(no/4)]} ${no%4+1}`:`${winds[Math.floor(no/4)]}${no%4+1}${language==='ja'?'局':'국'}`;
 return base+(honba?language==='en'?` · ${honba} honba`:language==='ja'?` ${honba}本場`:` ${honba}본장`:'');
};
globalThis.PaipuI18n=Object.freeze({t:translate,error,roundName,setLanguage,get language(){return language;},messages});
document.getElementById('languageSelect').addEventListener('change',e=>setLanguage(e.target.value));
apply();
})();
