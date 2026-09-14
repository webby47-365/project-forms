/* 도장·서명 이미지 생성기 — 무료서식 다운로드 (freeforms.kr)
 *
 * 모든 처리는 브라우저 캔버스 안에서만 이루어진다. 입력한 이름·그린 서명은 서버로
 * 전송되지 않으며 어디에도 저장되지 않는다(개인정보처리방침에 항목을 추가할 필요가 없다).
 *
 * 공개 API
 *   FFStamp.draw(canvas, opt)      도장을 캔버스에 그린다 (opt는 아래 DEFAULT 참고)
 *   FFStamp.download(canvas, name, kind)  PNG(투명) 또는 JPG(흰 배경)로 저장
 *   FFStamp.ready(cb)              웹폰트가 준비되면 cb 실행 (준비 전 그리면 대체 글꼴로 나온다)
 *   FFSign.attach(canvas, opts)    손글씨 서명 패드 생성 → {clear, undo, isEmpty, exportPng}
 *
 * 글꼴은 Google Fonts(구기·나눔명조·검은고딕·나눔펜)를 쓰고, 없으면 시스템 글꼴로 대체된다.
 * 印 글자는 한자라 한글 전용 웹폰트에 없으므로 시스템 글꼴(바탕·맑은 고딕)로 떨어진다.
 */
(function (root) {
  'use strict';

  /* hanja: 印 처럼 한글 웹폰트에 없는 글자를 그릴 시스템 글꼴. 웹폰트와 굵기가 맞도록
     fill 위에 stroke 를 한 번 더 그려 두껍게 만든다(strokeW = 글자 크기 대비 비율). */
  var FONT = {
    seal:     { css: '"Gugi","Malgun Gothic","맑은 고딕","Apple SD Gothic Neo",sans-serif', weight: '400', load: '"Gugi"',
                hanja: '"Malgun Gothic","맑은 고딕","Apple SD Gothic Neo","Noto Sans CJK KR",sans-serif', hanjaWeight: '700', strokeW: 0.045 },
    myeongjo: { css: '"Nanum Myeongjo","Batang","바탕",serif', weight: '800', load: '"Nanum Myeongjo"',
                hanja: '"Batang","바탕","Apple Myungjo","Noto Serif CJK KR",serif', hanjaWeight: '700', strokeW: 0.06 },
    gothic:   { css: '"Black Han Sans","Malgun Gothic","맑은 고딕",sans-serif', weight: '400', load: '"Black Han Sans"',
                hanja: '"Malgun Gothic","맑은 고딕","Apple SD Gothic Neo","Noto Sans CJK KR",sans-serif', hanjaWeight: '900', strokeW: 0.07 },
    pen:      { css: '"Nanum Pen Script","Malgun Gothic",cursive', weight: '400', load: '"Nanum Pen Script"' }
  };
  var HANJA_RE = /[\u4e00-\u9fff]/;

  /* 글자 하나를 그린다. 한자면 시스템 글꼴 + 외곽선으로 웹폰트 굵기에 맞춘다. */
  function glyph(ctx, ch, x, y, fs, f) {
    if (HANJA_RE.test(ch) && f.hanja) {
      ctx.font = f.hanjaWeight + ' ' + Math.round(fs) + 'px ' + f.hanja;
      ctx.lineWidth = fs * f.strokeW;
      ctx.lineJoin = 'round';
      ctx.strokeText(ch, x, y);
      ctx.fillText(ch, x, y);
      ctx.font = f.weight + ' ' + Math.round(fs) + 'px ' + f.css;
    } else {
      ctx.fillText(ch, x, y);
    }
  }
  var COLOR = { red: '#c8102e', blue: '#1d4ed8', black: '#1f2937', brown: '#b45309' };
  var DEFAULT = {
    name: '',            // 도장에 새길 이름 (1~4자 권장)
    shape: 'circle',     // circle | square | oval
    font: 'seal',        // seal | myeongjo | gothic
    color: 'red',        // COLOR 키 또는 CSS 색
    seal: true,          // 이름 뒤에 印 붙이기 (이름이 3자 이하일 때만)
    border: 'normal',    // thin | normal | bold
    size: 600            // 출력 해상도(px). 화면 표시 크기는 CSS가 정한다
  };

  function color(c) { return COLOR[c] || c || COLOR.red; }

  function sealChars(name, useSeal) {
    var chars = Array.from((name || '').replace(/\s+/g, '')).slice(0, 8);
    if (!chars.length) chars = Array.from('이름');
    if (useSeal && chars.length <= 3) chars.push('印');
    return chars;
  }

  function borderWidth(size, border) {
    var base = size * 0.036;
    if (border === 'thin') return base * 0.55;
    if (border === 'bold') return base * 1.5;
    return base;
  }

  /* 글자 배열 — 2~4자는 2열, 5자 이상은 3열. 한 줄에 놓이면 세로로 길어 보이므로
     1자·2자만 예외 처리한다(2자는 세로 1열). */
  function gridOf(n) {
    if (n <= 1) return { cols: 1, rows: 1 };
    if (n === 2) return { cols: 1, rows: 2 };
    if (n <= 4) return { cols: 2, rows: 2 };
    if (n <= 6) return { cols: 3, rows: 2 };
    return { cols: 3, rows: 3 };
  }

  function drawStamp(canvas, opt) {
    var o = Object.assign({}, DEFAULT, opt || {});
    var S = o.size, ctx = canvas.getContext('2d');
    var f = FONT[o.font] || FONT.seal;
    var col = color(o.color);
    var bw = borderWidth(S, o.border);
    var isOval = o.shape === 'oval';
    canvas.width = S;
    canvas.height = isOval ? Math.round(S * 0.66) : S;
    var W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.strokeStyle = col;
    ctx.fillStyle = col;
    ctx.lineWidth = bw;
    ctx.lineJoin = 'round';

    var pad = bw / 2 + S * 0.02;
    if (o.shape === 'square') {
      var r = S * 0.03;
      roundRect(ctx, pad, pad, W - pad * 2, H - pad * 2, r);
      ctx.stroke();
    } else if (isOval) {
      ctx.beginPath();
      ctx.ellipse(W / 2, H / 2, W / 2 - pad, H / 2 - pad, 0, 0, Math.PI * 2);
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.arc(W / 2, H / 2, W / 2 - pad, 0, Math.PI * 2);
      ctx.stroke();
    }

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    var chars;
    if (isOval) {
      // 타원은 이름을 가로 한 줄로 (회사 결재란·확인 도장 용도)
      var text = (o.name || '').replace(/\s+/g, '') || '이름';
      if (o.seal && Array.from(text).length <= 3) text += '印';
      var maxW = W - (bw + S * 0.06) * 2, fs = Math.min(H * 0.5, maxW / Math.max(1, Array.from(text).length) * 1.05);
      ctx.font = f.weight + ' ' + Math.round(fs) + 'px ' + f.css;
      // 글자마다 폭을 재서 이어 붙인다 (印 은 다른 글꼴이라 통째로 그리면 굵기가 어긋난다)
      var tchars = Array.from(text), widths = tchars.map(function (c) { return ctx.measureText(c).width; });
      var total = widths.reduce(function (a, b) { return a + b; }, 0), cx0 = W / 2 - total / 2;
      ctx.textAlign = 'left';
      for (var k = 0; k < tchars.length; k++) {
        glyph(ctx, tchars[k], cx0, H / 2 + fs * 0.04, fs, f);
        cx0 += widths[k];
      }
      ctx.textAlign = 'center';
    } else {
      chars = sealChars(o.name, o.seal);
      var g = gridOf(chars.length);
      var inset = o.shape === 'square' ? bw + S * 0.07 : bw + S * 0.13;
      var boxW = W - inset * 2, boxH = H - inset * 2;
      var cell = Math.min(boxW / g.cols, boxH / g.rows);
      var fsz = cell * (g.cols === 1 && g.rows === 1 ? 0.78 : 0.86);
      ctx.font = f.weight + ' ' + Math.round(fsz) + 'px ' + f.css;
      var x0 = W / 2 - (g.cols * cell) / 2 + cell / 2;
      var y0 = H / 2 - (g.rows * cell) / 2 + cell / 2;
      for (var i = 0; i < chars.length; i++) {
        var cx = x0 + (i % g.cols) * cell, cy = y0 + Math.floor(i / g.cols) * cell;
        // 3자(예: 홍길동 印 없음)는 아래 줄이 한 칸 비므로 가운데로 모은다
        if (chars.length === 3 && i === 2 && g.cols === 2) cx = W / 2;
        if (chars.length === 3 && i < 2 && g.cols === 2) { /* 윗줄 두 글자는 그대로 */ }
        glyph(ctx, chars[i], cx, cy + fsz * 0.05, fsz, f);
      }
    }
    return canvas;
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  /* 저장 — kind: 'png'(투명 배경) | 'jpg'(흰 배경). 파일명은 한글 그대로 쓴다. */
  function download(canvas, filename, kind) {
    var src = canvas;
    if (kind === 'jpg') {
      src = document.createElement('canvas');
      src.width = canvas.width; src.height = canvas.height;
      var c = src.getContext('2d');
      c.fillStyle = '#fff'; c.fillRect(0, 0, src.width, src.height);
      c.drawImage(canvas, 0, 0);
    }
    var mime = kind === 'jpg' ? 'image/jpeg' : 'image/png';
    var done = function (blob) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url; a.download = filename + (kind === 'jpg' ? '.jpg' : '.png');
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 1500);
    };
    if (src.toBlob) src.toBlob(done, mime, 0.95);
    else { // 아주 오래된 브라우저
      var a = document.createElement('a');
      a.href = src.toDataURL(mime, 0.95); a.download = filename + '.' + (kind === 'jpg' ? 'jpg' : 'png');
      document.body.appendChild(a); a.click(); a.remove();
    }
    if (typeof root.gtag === 'function') {
      root.gtag('event', 'tool_download', { tool: 'stamp', kind: kind || 'png' });
    }
  }

  /* 웹폰트 로드 대기. 글꼴이 늦게 오면 처음 그린 도장이 시스템 글꼴로 나오므로,
     준비된 뒤 한 번 더 그리게 한다. document.fonts가 없는 브라우저는 즉시 실행. */
  function ready(cb) {
    if (!(document.fonts && document.fonts.load)) { cb(); return; }
    var loads = Object.keys(FONT).map(function (k) {
      return document.fonts.load(FONT[k].weight + ' 40px ' + FONT[k].load).catch(function () {});
    });
    Promise.all(loads).then(function () { cb(); }, function () { cb(); });
    // 네트워크가 막혀 있어도 2.5초 뒤에는 그린다
    setTimeout(cb, 2500);
  }

  root.FFStamp = { draw: drawStamp, download: download, ready: ready, COLOR: COLOR, FONT: FONT, DEFAULT: DEFAULT };

  /* ── 손글씨 서명 패드 ── */
  function attachSign(canvas, opts) {
    var o = Object.assign({ color: '#1b2a44', width: 3.2 }, opts || {});
    var ctx = canvas.getContext('2d');
    var dpr = Math.max(1, root.devicePixelRatio || 1);
    var strokes = [], cur = null, drawing = false;

    function fit() {
      var rect = canvas.getBoundingClientRect();
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
      redraw();
    }
    function pos(ev) {
      var rect = canvas.getBoundingClientRect();
      var p = ev.touches ? ev.touches[0] : ev;
      return { x: (p.clientX - rect.left) * dpr, y: (p.clientY - rect.top) * dpr };
    }
    function stroke(s) {
      if (s.pts.length < 2) {
        ctx.beginPath(); ctx.arc(s.pts[0].x, s.pts[0].y, s.w * dpr / 2, 0, Math.PI * 2);
        ctx.fillStyle = s.c; ctx.fill(); return;
      }
      ctx.strokeStyle = s.c; ctx.lineWidth = s.w * dpr;
      ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      ctx.beginPath();
      ctx.moveTo(s.pts[0].x, s.pts[0].y);
      for (var i = 1; i < s.pts.length - 1; i++) {
        var mx = (s.pts[i].x + s.pts[i + 1].x) / 2, my = (s.pts[i].y + s.pts[i + 1].y) / 2;
        ctx.quadraticCurveTo(s.pts[i].x, s.pts[i].y, mx, my);
      }
      var last = s.pts[s.pts.length - 1];
      ctx.lineTo(last.x, last.y);
      ctx.stroke();
    }
    function redraw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      strokes.forEach(stroke);
      if (cur) stroke(cur);
      canvas.dispatchEvent(new CustomEvent('ffsign', { detail: { empty: !strokes.length && !cur } }));
    }
    function down(ev) {
      ev.preventDefault();
      drawing = true;
      cur = { pts: [pos(ev)], c: o.color, w: o.width };
      redraw();
    }
    function move(ev) {
      if (!drawing) return;
      ev.preventDefault();
      cur.pts.push(pos(ev));
      redraw();
    }
    function up() {
      if (!drawing) return;
      drawing = false;
      if (cur) strokes.push(cur);
      cur = null;
      redraw();
    }
    canvas.style.touchAction = 'none';
    canvas.addEventListener('pointerdown', down);
    canvas.addEventListener('pointermove', move);
    root.addEventListener('pointerup', up);
    root.addEventListener('pointercancel', up);
    root.addEventListener('resize', fit);
    fit();

    return {
      clear: function () { strokes = []; cur = null; redraw(); },
      undo: function () { strokes.pop(); redraw(); },
      isEmpty: function () { return !strokes.length; },
      setColor: function (c) { o.color = c; },
      setWidth: function (w) { o.width = w; },
      /* 획이 있는 부분만 잘라 투명 PNG 캔버스로 돌려준다 */
      exportCanvas: function () {
        var out = document.createElement('canvas');
        if (!strokes.length) { out.width = out.height = 1; return out; }
        var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        strokes.forEach(function (s) { s.pts.forEach(function (p) {
          minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
          minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
        }); });
        var m = 14 * dpr;
        var w = Math.max(1, Math.round(maxX - minX + m * 2)), h = Math.max(1, Math.round(maxY - minY + m * 2));
        out.width = w; out.height = h;
        var c = out.getContext('2d');
        c.drawImage(canvas, minX - m, minY - m, w, h, 0, 0, w, h);
        return out;
      }
    };
  }

  root.FFSign = { attach: attachSign };
})(window);
