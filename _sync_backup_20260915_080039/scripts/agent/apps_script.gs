/**
 * 무료서식 다운로드 — 방문자 서식 요청 접수 (구글 Apps Script)
 *
 * 하는 일
 *   1) 사이트의 요청 폼에서 온 내용을 구글 시트에 기록한다
 *   2) 상한에 걸리지 않으면 GitHub에 "지금 만들어라" 신호를 보낸다 → 5~7분 내 사이트 반영
 *   3) 상한을 넘으면 시트에만 쌓아 두고, 다음 날 아침 08:00 작업이 가져간다
 *
 * 받는 항목은 서식 이름과 용도뿐이다. 이름·연락처·이메일은 받지 않는다(개인정보 미수집).
 *
 * ─── 설치 순서 ───────────────────────────────────────────────
 *  1. 구글 드라이브에서 스프레드시트를 새로 만든다 (이름: 무료서식 요청함)
 *  2. 확장 프로그램 → Apps Script → 이 파일 내용을 통째로 붙여넣는다
 *  3. 왼쪽 톱니바퀴(프로젝트 설정) → 스크립트 속성에 아래 두 개를 추가한다
 *       GITHUB_REPO   = webby47-365/project-forms
 *       GITHUB_TOKEN  = (GitHub 세밀한 권한 토큰, Contents 읽기·쓰기)
 *  4. 배포 → 새 배포 → 유형 "웹 앱"
 *       실행 계정 = 나,  액세스 권한 = 모든 사용자
 *  5. 배포 후 나오는 주소(/exec 로 끝남)를 catalog/requests.json 의 endpoint 에 넣는다
 * ────────────────────────────────────────────────────────────
 */

// ── 설정값 ────────────────────────────────────────────────────
var SITE = 'https://freeforms.kr';
var SHEET_NAME = '요청';
var MAX_TITLE = 40;
var MAX_PURPOSE = 120;
var LIMIT_PER_HOUR = 3;   // 시간당 즉시 제작 건수
var LIMIT_PER_DAY = 10;   // 하루 즉시 제작 건수
var DEDUPE_HOURS = 24;    // 같은 요청을 하나로 합치는 기간

// ── 접수 (사이트 폼에서 호출) ─────────────────────────────────
function doPost(e) {
  try {
    var body = JSON.parse((e && e.postData && e.postData.contents) || '{}');

    // 봇 차단: 사람에게는 보이지 않는 칸이 채워져 있으면 자동 제출이다
    if (String(body.hp || '').length > 0) {
      return json({ ok: true, immediate: false });  // 봇에게는 성공한 것처럼 보이게 둔다
    }

    var title = clean(body.title, MAX_TITLE);
    var purpose = clean(body.purpose, MAX_PURPOSE);
    if (title.length < 2) {
      return json({ ok: false, message: '서식 이름을 두 글자 이상 적어 주세요.' });
    }
    if (!/[가-힣a-zA-Z]/.test(title)) {
      return json({ ok: false, message: '서식 이름을 글자로 적어 주세요.' });
    }

    var sheet = getSheet();
    var now = new Date();

    // 이미 있는 서식이면 만들지 않고 바로 안내한다
    var exists = findExistingForm(title);
    if (exists) {
      sheet.appendRow([now, title, purpose, '이미있음', exists, '']);
      return json({ ok: true, existing: exists });
    }

    // 같은 요청이 최근에 들어왔으면 한 건으로 합친다
    if (isDuplicate(sheet, title, now)) {
      sheet.appendRow([now, title, purpose, '중복', '', '']);
      return json({ ok: true, duplicate: true });
    }

    var immediate = withinLimit(sheet, now);
    sheet.appendRow([now, title, purpose, immediate ? '즉시' : '대기', '', '']);

    if (immediate) {
      var sent = dispatchToGithub(title, purpose);
      if (!sent) {
        // 신호를 못 보내도 요청은 남아 있으므로 다음 날 아침에 처리된다
        sheet.getRange(sheet.getLastRow(), 4).setValue('대기(신호실패)');
        immediate = false;
      }
    }
    return json({ ok: true, immediate: immediate });

  } catch (err) {
    return json({ ok: false, message: '접수 중 오류가 발생했습니다. 잠시 뒤 다시 시도해 주세요.' });
  }
}

// ── 조회 (08:00 일일 작업이 대기분을 가져간다) ────────────────
function doGet(e) {
  try {
    var sheet = getSheet();
    var rows = sheet.getDataRange().getValues();
    var out = [];
    for (var i = 1; i < rows.length; i++) {
      if (String(rows[i][3]) !== '대기' && String(rows[i][3]) !== '대기(신호실패)') continue;
      out.push({
        ts: rows[i][0] ? new Date(rows[i][0]).toISOString() : '',
        title: String(rows[i][1] || ''),
        purpose: String(rows[i][2] || '')
      });
    }
    return json({ ok: true, pending: out.slice(-30) });
  } catch (err) {
    return json({ ok: false, pending: [] });
  }
}

// ── 도우미 ────────────────────────────────────────────────────

/** 시트를 가져온다. 없으면 머리글과 함께 만든다. */
function getSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(['시각', '서식 이름', '용도', '상태', '기존 서식', '비고']);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

/** 앞뒤 공백·줄바꿈을 지우고 길이를 자른다. */
function clean(v, max) {
  return String(v == null ? '' : v).replace(/[\r\n\t]+/g, ' ').trim().slice(0, max);
}

/** 비교용으로 공백을 없애고 소문자로 만든다. */
function norm(s) {
  return String(s).toLowerCase().replace(/\s+/g, '');
}

/**
 * 사이트의 검색 색인에서 같은 뜻의 서식을 찾는다.
 * 색인은 10분간 캐시해 매 요청마다 내려받지 않는다.
 */
function findExistingForm(title) {
  var cache = CacheService.getScriptCache();
  var raw = cache.get('index');
  if (!raw) {
    try {
      raw = UrlFetchApp.fetch(SITE + '/search-index.json', { muteHttpExceptions: true }).getContentText();
      cache.put('index', raw, 600);
    } catch (err) {
      return '';   // 색인을 못 읽으면 중복 검사를 건너뛴다
    }
  }
  var forms = (JSON.parse(raw) || {}).forms || [];
  var key = norm(title);
  for (var i = 0; i < forms.length; i++) {
    var t = norm(forms[i].title);
    // 제목이 서로를 품고 있으면 같은 서식으로 본다 ("이력서" ↔ "이력서 (기본형)")
    if (t === key || t.indexOf(key) >= 0 || key.indexOf(t) >= 0) return forms[i].id;
  }
  return '';
}

/** 최근 DEDUPE_HOURS 안에 같은 이름의 요청이 있었는지 확인한다. */
function isDuplicate(sheet, title, now) {
  var rows = sheet.getDataRange().getValues();
  var key = norm(title);
  var since = now.getTime() - DEDUPE_HOURS * 3600 * 1000;
  for (var i = rows.length - 1; i >= 1; i--) {
    var ts = rows[i][0] ? new Date(rows[i][0]).getTime() : 0;
    if (ts < since) break;
    if (norm(rows[i][1]) === key) return true;
  }
  return false;
}

/** 즉시 제작 상한(시간당·하루) 안에 있는지 확인한다. */
function withinLimit(sheet, now) {
  var rows = sheet.getDataRange().getValues();
  var hourAgo = now.getTime() - 3600 * 1000;
  var dayAgo = now.getTime() - 24 * 3600 * 1000;
  var hour = 0, day = 0;
  for (var i = rows.length - 1; i >= 1; i--) {
    var ts = rows[i][0] ? new Date(rows[i][0]).getTime() : 0;
    if (ts < dayAgo) break;
    if (String(rows[i][3]).indexOf('즉시') !== 0) continue;
    day++;
    if (ts >= hourAgo) hour++;
  }
  return hour < LIMIT_PER_HOUR && day < LIMIT_PER_DAY;
}

/** GitHub에 "지금 만들어라" 신호를 보낸다. 성공하면 true. */
function dispatchToGithub(title, purpose) {
  var props = PropertiesService.getScriptProperties();
  var repo = props.getProperty('GITHUB_REPO');
  var token = props.getProperty('GITHUB_TOKEN');
  if (!repo || !token) return false;

  var res = UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/dispatches', {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'Authorization': 'Bearer ' + token,
      'Accept': 'application/vnd.github+json'
    },
    payload: JSON.stringify({
      event_type: 'form-request',
      client_payload: { title: title, purpose: purpose }
    }),
    muteHttpExceptions: true
  });
  return res.getResponseCode() === 204;
}

/** JSON 응답. */
function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/** 설치 확인용. 편집기에서 직접 실행해 보면 신호가 가는지 확인할 수 있다. */
function testDispatch() {
  Logger.log(dispatchToGithub('시험 요청 서식', '설치 확인용'));
}
