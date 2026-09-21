/* INTENT: 원본 페이지는 탐색 기준으로, 화면 단은 넘김 단위로 사용한다.
   글꼴이나 화면 크기가 바뀌어도 문장을 건너뛰지 않고 읽던 앵커를 복원한다. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const book = JSON.parse($("book-data").textContent);
  const contentCSS = JSON.parse($("content-style").textContent);
  const frame = $("book-frame");
  const key = `offline-reader:${book.id}:v1`;
  const defaults = {dark:false, font:"original", size:100, line:100, align:"left", layout:"auto"};
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(key) || "{}") || {}; } catch (_) { /* 저장소가 막혀도 현재 창에서 읽기는 계속한다. */ }
  const settings = {...defaults, ...saved.settings};
  settings.size = clamp(Number(settings.size) || 100, 70, 180);
  settings.line = clamp(Number(settings.line) || 100, 70, 160);
  if (!["original","sans","serif","system"].includes(settings.font)) settings.font = "original";
  if (!["auto","single","double"].includes(settings.layout)) settings.layout = "auto";
  if (!["left","justify"].includes(settings.align)) settings.align = "left";
  let bookmarks = Array.isArray(saved.bookmarks) ? saved.bookmarks.filter(b => book.chapters[b.chapter]) : [];
  let chapterIndex = -1, spread = 0, spreads = 1, columns = 1, stride = 1, page = 0;
  let locationMark = null, anchors = [], pageMarks = [], tocMarks = [];
  let activeTOC = -1, openPanel = null, navigationVersion = 0, busy = false;
  let resizeTimer, noticeTimer, searchTimer, searchIndex;
  const chapterURLs = book.chapters.map(c => new URL(c.file, location.href).href);

  function persist() {
    try { localStorage.setItem(key, JSON.stringify({settings, bookmarks, location:locationMark})); }
    catch (_) { /* 비공개 모드 등 저장 실패가 페이지 이동을 막지 않도록 한다. */ }
  }
  function notify(message) {
    $("notice").textContent = message; $("notice").hidden = false;
    clearTimeout(noticeTimer); noticeTimer = setTimeout(() => { $("notice").hidden = true; }, 2600);
  }
  function closePanels(restoreFocus = false) {
    for (const name of ["settings","toc","search"]) {
      $(`${name}-panel`).hidden = true;
      $(`${name}-toggle`).setAttribute("aria-expanded", "false");
    }
    if (restoreFocus && openPanel) $(`${openPanel}-toggle`).focus();
    openPanel = null;
  }
  function togglePanel(name) {
    const wasOpen = openPanel === name;
    closePanels();
    if (wasOpen) return;
    openPanel = name;
    $(`${name}-panel`).hidden = false;
    $(`${name}-toggle`).setAttribute("aria-expanded", "true");
    if (name === "search") $("search-input").focus();
    if (name === "toc") {
      renderBookmarks();
      $("toc-list").querySelector('[aria-current="true"]')?.scrollIntoView({block:"center"});
    }
  }
  for (const name of ["settings","toc","search"]) $(`${name}-toggle`).addEventListener("click", () => togglePanel(name));
  document.querySelectorAll(".close-panel").forEach(b => b.addEventListener("click", () => closePanels(true)));
  document.addEventListener("pointerdown", event => {
    if (openPanel && !event.target.closest(".panel,.toolbar")) closePanels();
  });

  function syncSettings() {
    document.documentElement.dataset.theme = settings.dark ? "dark" : "light";
    $("dark-theme").setAttribute("aria-checked", String(!!settings.dark));
    $("font-family").value = settings.font;
    $("font-value").value = `${settings.size}%`;
    $("line-value").value = `${settings.line}%`;
    $("font-less").disabled = settings.size <= 70; $("font-more").disabled = settings.size >= 180;
    $("line-less").disabled = settings.line <= 70; $("line-more").disabled = settings.line >= 160;
    document.querySelectorAll("[data-align]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.align === settings.align)));
    document.querySelectorAll("[data-layout]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.layout === settings.layout)));
    columns = settings.layout === "double" || (settings.layout === "auto" && innerWidth >= 1100) ? 2 : 1;
    $("paper").classList.toggle("double", columns === 2);
  }
  function styleDocument() {
    const doc = frame.contentDocument;
    if (!doc?.getElementById("reader-flow")) return;
    const root = doc.documentElement;
    root.dataset.theme = settings.dark ? "dark" : "light"; root.dataset.font = settings.font;
    root.style.setProperty("--paper", settings.dark ? "#24262b" : "#ffffff");
    root.style.setProperty("--ink", settings.dark ? "#e3e4e7" : "#25282b");
    root.style.setProperty("--reader-size", `${20 * settings.size / 100}px`);
    root.style.setProperty("--reader-line", String(1.9 * settings.line / 100));
    root.style.setProperty("--reader-align", settings.align);
    root.style.setProperty("--columns", String(columns));
    root.style.setProperty("--image-height", `${Math.max(60, doc.getElementById("reading-window").clientHeight - 8)}px`);
  }
  async function changeSettings(change) {
    const previous = locationMark;
    Object.assign(settings, change); syncSettings(); styleDocument(); persist();
    if (chapterIndex < 0 || busy) return;
    await frame.contentDocument.fonts.ready;
    measure(); goToAnchor(previous?.anchor || "");
  }
  $("dark-theme").addEventListener("click", () => changeSettings({dark:!settings.dark}));
  $("font-family").addEventListener("change", event => changeSettings({font:event.target.value}));
  for (const [id, field, step, min, max] of [["font-less","size",-10,70,180],["font-more","size",10,70,180],["line-less","line",-10,70,160],["line-more","line",10,70,160]]) {
    $(id).addEventListener("click", () => changeSettings({[field]:clamp(settings[field]+step,min,max)}));
  }
  document.querySelectorAll("[data-align]").forEach(b => b.addEventListener("click", () => changeSettings({align:b.dataset.align})));
  document.querySelectorAll("[data-layout]").forEach(b => b.addEventListener("click", () => changeSettings({layout:b.dataset.layout})));

  function elementColumn(element) {
    if (!element) return 0;
    const doc = frame.contentDocument, flow = doc.getElementById("reader-flow");
    let rect = element.getClientRects()[0];
    if (!rect) {
      const next = doc.createTreeWalker(flow, NodeFilter.SHOW_ELEMENT);
      next.currentNode = element;
      let candidate;
      while ((candidate = next.nextNode())) {
        rect = candidate.getClientRects()[0];
        if (rect) break;
      }
    }
    return rect ? Math.max(0, Math.floor((rect.left - flow.getBoundingClientRect().left + 1) / stride)) : 0;
  }
  function measure() {
    const doc = frame.contentDocument, flow = doc.getElementById("reader-flow");
    flow.style.transform = "none";
    const gap = parseFloat(frame.contentWindow.getComputedStyle(flow).columnGap) || 0;
    // clientWidth rounds to whole pixels. Repeated across many columns, that
    // rounding can send a marker near a column boundary to the previous spread.
    stride = (flow.getBoundingClientRect().width + gap) / columns;
    spreads = Math.max(1, Math.ceil((flow.scrollWidth + gap - 1) / (stride * columns)));
    const top = doc.getElementById("reading-window").getBoundingClientRect().top;
    anchors = [...flow.querySelectorAll("[id]")].map((el, order) => ({anchor:el.id, column:elementColumn(el), top:(el.getClientRects()[0]?.top ?? top)-top, order}));
    const anchorMap = new Map(anchors.map(a => [a.anchor, a]));
    pageMarks = book.pages.map((p,i) => ({...p,index:i,...anchorMap.get(p.anchor)})).filter(p => p.chapter === chapterIndex);
    tocMarks = book.toc.map((t,i) => ({...t,index:i,...anchorMap.get(t.anchor)})).filter(t => t.chapter === chapterIndex);
  }
  function tocForPage(index) {
    let result = book.toc[0];
    for (const entry of book.toc) { if (entry.page <= index) result = entry; else break; }
    return result?.label || book.title;
  }
  function updateTooltip(index) {
    $("page-tooltip").textContent = `${tocForPage(index)} - ${book.pages[index].label}페이지`;
  }
  function updatePosition(preferredAnchor = "") {
    const firstColumn = spread * columns;
    const preferred = anchors.find(a => a.anchor === preferredAnchor);
    const reached = mark => preferred ? mark.order <= preferred.order : mark.column < firstColumn || (mark.column === firstColumn && mark.top <= 2);
    const firstPage = book.pages.findLastIndex(p => p.chapter < chapterIndex);
    const visiblePage = pageMarks.findLast(reached);
    page = visiblePage?.index ?? Math.max(0, firstPage);
    const startsBeforeScreen = mark => mark.column < firstColumn || (mark.column === firstColumn && mark.top <= 2);
    const rangeStart = Math.min(page, pageMarks.findLast(startsBeforeScreen)?.index ?? Math.max(0, firstPage));
    const rangeEnd = Math.max(rangeStart, pageMarks.findLast(mark => mark.column < firstColumn + columns)?.index ?? rangeStart);
    const visibleAnchor = preferredAnchor || anchors.find(a => a.column >= firstColumn)?.anchor || anchors.at(-1)?.anchor || "";
    const priorTOC = book.toc.findLastIndex(t => t.chapter < chapterIndex);
    activeTOC = tocMarks.findLast(reached)?.index ?? priorTOC;
    if (preferredAnchor && book.pages[page].anchor === preferredAnchor) {
      activeTOC = book.toc.findLastIndex(t => t.page <= page);
    }
    locationMark = {chapter:chapterIndex, anchor:visibleAnchor, page, label:book.toc[activeTOC]?.label || book.chapters[chapterIndex].title};
    $("page-slider").value = String(rangeStart + 1); $("page-number").value = String(rangeStart + 1);
    $("page-end").textContent = `–${book.pages[rangeEnd].label}`;
    $("page-end").hidden = rangeEnd <= rangeStart;
    $("page-slider").style.setProperty("--progress", `${rangeStart / Math.max(1, book.pages.length - 1) * 100}%`);
    $("page-slider").setAttribute("aria-valuetext", `${book.pages[rangeStart].label}${rangeEnd > rangeStart ? '–'+book.pages[rangeEnd].label : ''} / ${book.pages.length}페이지`);
    updateTooltip(rangeStart);
    $("previous").disabled = chapterIndex === 0 && spread === 0;
    $("next").disabled = chapterIndex === book.chapters.length - 1 && spread === spreads - 1;
    [...$("toc-list").children].forEach((row, i) => row.setAttribute("aria-current", String(i === activeTOC)));
    syncBookmark(); persist();
    document.body.dataset.ready = "true";
    document.body.dataset.chapter = String(chapterIndex);
    document.body.dataset.spread = String(spread);
    document.body.dataset.spreads = String(spreads);
    document.body.dataset.pageStart = String(rangeStart + 1);
    document.body.dataset.pageEnd = String(rangeEnd + 1);
  }
  function showSpread(next, preferredAnchor = "") {
    spread = clamp(next, 0, spreads - 1);
    frame.contentDocument.getElementById("reader-flow").style.transform = `translateX(${-spread * stride * columns}px)`;
    updatePosition(preferredAnchor);
  }
  function goToAnchor(anchor, end = false) {
    const column = anchors.find(a => a.anchor === anchor)?.column || 0;
    showSpread(end ? spreads - 1 : Math.floor(column / columns), anchor);
  }
  async function navigate(chapter, anchor = "", end = false) {
    if (!book.chapters[chapter]) return;
    closePanels();
    if (chapter === chapterIndex && !busy) { goToAnchor(anchor, end); return; }
    const version = ++navigationVersion;
    busy = true; $("loading").hidden = false; document.body.dataset.ready = "false";
    const entry = book.chapters[chapter];
    await new Promise(resolve => {
      frame.onload = resolve;
      frame.srcdoc = `<!doctype html><html lang="${escapeHTML(book.language)}"><head><meta charset="utf-8"><base href="${escapeHTML(chapterURLs[chapter])}">${entry.styles.map(h => `<link rel="stylesheet" href="${escapeHTML(h)}">`).join("")}<style>${contentCSS}</style></head><body class="book-content"><div id="reading-window"><main id="reader-flow">${entry.html}</main></div></body></html>`;
    });
    if (version !== navigationVersion) return;
    chapterIndex = chapter;
    const doc = frame.contentDocument;
    // Some original page markers live in empty display:none wrappers. Expose
    // only those empty wrappers so they get a column without revealing content.
    for (const el of doc.querySelectorAll('[style*="display:none"], [style*="display: none"]')) {
      if (!el.textContent.trim() && el.querySelector("[id]") && !el.querySelector("img,svg")) el.classList.add("reader-position");
    }
    styleDocument();
    await doc.fonts.ready;
    if (version !== navigationVersion) return;
    measure(); busy = false; goToAnchor(anchor, end); $("loading").hidden = true;
    doc.addEventListener("keydown", handleKey);
    doc.addEventListener("pointerdown", () => closePanels());
    doc.addEventListener("click", event => {
      const link = event.target.closest("a[href]");
      if (!link) return;
      const url = new URL(link.getAttribute("href"), chapterURLs[chapterIndex]);
      const fragment = decodeURIComponent(url.hash.slice(1)); url.hash = "";
      const target = chapterURLs.indexOf(url.href);
      if (target >= 0) { event.preventDefault(); navigate(target, fragment); }
      else if (["https:","http:","mailto:"].includes(url.protocol)) { event.preventDefault(); window.open(url.href + (fragment ? "#"+fragment : ""), "_blank", "noopener"); }
    });
    let wheelAmount = 0, wheelLast = 0;
    doc.addEventListener("wheel", event => {
      if (event.ctrlKey || event.metaKey || openPanel) return;
      event.preventDefault();
      const now = performance.now();
      if (now - wheelLast < 400) return;
      wheelAmount += event.deltaY || event.deltaX;
      if (Math.abs(wheelAmount) > 70) { turn(wheelAmount > 0 ? 1 : -1); wheelAmount = 0; wheelLast = now; }
    }, {passive:false});
    let touchStart;
    doc.addEventListener("touchstart", e => { touchStart = e.touches.length === 1 ? {x:e.touches[0].clientX,y:e.touches[0].clientY} : null; }, {passive:true});
    doc.addEventListener("touchend", e => {
      if (!touchStart || doc.getSelection()?.toString()) return;
      const dx = e.changedTouches[0].clientX - touchStart.x, dy = e.changedTouches[0].clientY - touchStart.y;
      if (Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy)*1.5) turn(dx < 0 ? 1 : -1);
      touchStart = null;
    });
  }
  function turn(direction) {
    if (busy) return;
    if (spread + direction < 0) navigate(chapterIndex - 1, "", true);
    else if (spread + direction >= spreads) navigate(chapterIndex + 1);
    else showSpread(spread + direction);
  }
  function handleKey(event) {
    if (event.key === "Escape") { closePanels(true); return; }
    if (event.target.closest("input,select,textarea,button,[contenteditable]")) return;
    if (event.ctrlKey || event.metaKey || event.altKey || openPanel) return;
    if (["ArrowRight","PageDown"," "].includes(event.key)) { event.preventDefault(); turn(event.shiftKey ? -1 : 1); }
    if (["ArrowLeft","PageUp"].includes(event.key)) { event.preventDefault(); turn(-1); }
  }
  document.addEventListener("keydown", handleKey);
  $("previous").addEventListener("click", () => turn(-1)); $("next").addEventListener("click", () => turn(1));
  $("page-slider").max = $("page-number").max = String(book.pages.length);
  $("page-total").textContent = `/ ${book.pages.length}`;
  $("page-slider").addEventListener("input", e => updateTooltip(Number(e.target.value)-1));
  function jumpPage(value) {
    const destination = book.pages[clamp(Math.round(Number(value)||1)-1, 0, book.pages.length-1)];
    navigate(destination.chapter, destination.anchor);
  }
  $("page-slider").addEventListener("change", event => jumpPage(event.target.value));
  $("page-form").addEventListener("submit", event => { event.preventDefault(); jumpPage($("page-number").value); $("page-number").blur(); });

  function makeEntry(label, index, depth = 0) {
    const button = document.createElement("button"); button.className = "entry";
    button.style.setProperty("--depth", String(Math.min(depth, 4)));
    const title = document.createElement("span"); title.className = "entry-title"; title.textContent = label;
    const number = document.createElement("span"); number.className = "entry-page"; number.textContent = `${book.pages[index]?.label || index+1}페이지`;
    button.append(title, number); button.title = label;
    return button;
  }
  book.toc.forEach(entry => {
    const button = makeEntry(entry.label, entry.page, entry.depth);
    button.addEventListener("click", () => navigate(entry.chapter, entry.anchor)); $("toc-list").append(button);
  });
  function selectTab(bookmarksSelected) {
    for (const name of ["toc","bookmarks"]) {
      const selected = (name === "bookmarks") === bookmarksSelected;
      $(`${name}-tab`).setAttribute("aria-selected", String(selected));
      $(`${name}-tab`).tabIndex = selected ? 0 : -1; $(`${name}-list`).hidden = !selected;
    }
    if (bookmarksSelected) renderBookmarks();
  }
  $("toc-tab").addEventListener("click", () => selectTab(false)); $("bookmarks-tab").addEventListener("click", () => selectTab(true));
  for (const id of ["toc-tab","bookmarks-tab"]) $(id).addEventListener("keydown", event => {
    if (["ArrowLeft","ArrowRight","Home","End"].includes(event.key)) {
      event.preventDefault(); const showBookmarks = event.key === "End" || (event.key !== "Home" && id === "toc-tab");
      selectTab(showBookmarks); $(showBookmarks ? "bookmarks-tab" : "toc-tab").focus();
    }
  });
  function sameBookmark(mark) {
    const column = anchors.find(a => a.anchor === mark.anchor)?.column;
    return mark.chapter === chapterIndex && (mark.anchor === locationMark?.anchor || (column !== undefined && Math.floor(column / columns) === spread));
  }
  function syncBookmark() { $("bookmark-toggle").setAttribute("aria-pressed", String(bookmarks.some(sameBookmark))); }
  function renderBookmarks() {
    $("bookmarks-list").replaceChildren();
    if (!bookmarks.length) { const p = document.createElement("p"); p.className="empty"; p.textContent="읽던 곳을 남기려면 상단의 북마크 버튼을 누르세요."; $("bookmarks-list").append(p); return; }
    for (const mark of [...bookmarks].sort((a,b) => a.page-b.page)) {
      const row = document.createElement("div"); row.className = "bookmark-row";
      const button = makeEntry(mark.label, mark.page); button.addEventListener("click", () => navigate(mark.chapter, mark.anchor));
      const remove = document.createElement("button"); remove.className = "icon-button"; remove.setAttribute("aria-label", `${mark.label} 북마크 삭제`); remove.innerHTML='<svg><use href="#i-close"/></svg>';
      remove.addEventListener("click", () => { bookmarks = bookmarks.filter(b => b !== mark); persist(); renderBookmarks(); syncBookmark(); });
      row.append(button, remove); $("bookmarks-list").append(row);
    }
  }
  $("bookmark-toggle").addEventListener("click", () => {
    if (!locationMark) return;
    const existing = bookmarks.some(sameBookmark);
    if (existing) bookmarks = bookmarks.filter(mark => !sameBookmark(mark)); else bookmarks.push({...locationMark});
    persist(); syncBookmark(); renderBookmarks(); notify(existing ? "북마크를 삭제했습니다." : "현재 위치를 북마크에 저장했습니다.");
  });

  function prepareSearch() {
    if (searchIndex) return;
    searchIndex = [];
    const parser = new DOMParser();
    const pageMap = new Map(book.pages.map((p, i) => [p.href, i]));
    let currentPage = 0;
    book.chapters.forEach((chapter, index) => {
      const doc = parser.parseFromString(chapter.html, "text/html");
      const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
      let node, anchor = chapter.first_id || "", text = "", block, blockAnchor = anchor, blockPage = currentPage;
      function flush() { if (text.trim()) searchIndex.push({text:text.trim(),chapter:index,anchor:blockAnchor,page:blockPage}); text=""; }
      while ((node = walker.nextNode())) {
        if (node.nodeType === Node.ELEMENT_NODE && node.id) {
          anchor=node.id; currentPage=pageMap.get(`${chapter.file}#${node.id}`) ?? currentPage;
        } else if (node.nodeType === Node.TEXT_NODE) {
          const parent = node.parentElement.closest("p,pre,li,h1,h2,h3,h4,td,th") || node.parentElement;
          if (parent !== block) { flush(); block=parent; blockAnchor=anchor; blockPage=currentPage; }
          text += node.textContent;
        }
      }
      flush();
    });
  }
  async function search() {
    const query = $("search-input").value.trim(); $("search-results").replaceChildren();
    if (!query) { $("search-status").textContent="책 전체에서 검색합니다."; return; }
    prepareSearch(); const needle=query.toLocaleLowerCase();
    const results=searchIndex.filter(entry => entry.text.toLocaleLowerCase().includes(needle));
    $("search-status").textContent=`${results.length}개 결과${results.length > 100 ? " 중 앞 100개를 표시합니다." : ""}`;
    for (const result of results.slice(0, 100)) {
      const at=result.text.toLocaleLowerCase().indexOf(needle), start=Math.max(0,at-34), end=Math.min(result.text.length,at+query.length+65);
      const button=makeEntry("",result.page), title=button.querySelector(".entry-title");
      title.append(document.createTextNode((start ? "…" : "") + result.text.slice(start,at)));
      const mark=document.createElement("mark"); mark.textContent=result.text.slice(at,at+query.length); title.append(mark,document.createTextNode(result.text.slice(at+query.length,end)+(end<result.text.length ? "…" : "")));
      button.addEventListener("click",async () => { await navigate(result.chapter,result.anchor); highlightSearch(query); }); $("search-results").append(button);
    }
  }
  function highlightSearch(query) {
    const doc=frame.contentDocument;
    for (const mark of doc.querySelectorAll("mark.reader-match")) mark.replaceWith(...mark.childNodes);
    const walker=doc.createTreeWalker(doc.getElementById("reader-flow"),NodeFilter.SHOW_TEXT); const nodes=[];
    let node; while ((node=walker.nextNode())) if (node.textContent.toLocaleLowerCase().includes(query.toLocaleLowerCase())) nodes.push(node);
    for (const text of nodes) {
      const at=text.textContent.toLocaleLowerCase().indexOf(query.toLocaleLowerCase());
      const range=doc.createRange();range.setStart(text,at);range.setEnd(text,at+query.length);
      const mark=doc.createElement("mark");mark.className="reader-match";range.surroundContents(mark);
    }
  }
  $("search-form").addEventListener("submit",event => {event.preventDefault();search();});
  $("search-input").addEventListener("input",() => {clearTimeout(searchTimer);searchTimer=setTimeout(search,200);});
  $("fullscreen").addEventListener("click",async () => {
    try { if (document.fullscreenElement) await document.exitFullscreen(); else await document.documentElement.requestFullscreen(); }
    catch (_) { notify("이 브라우저에서는 전체 화면을 열 수 없습니다."); }
  });
  window.addEventListener("resize",() => {
    clearTimeout(resizeTimer); resizeTimer=setTimeout(async () => {
      if (busy || chapterIndex<0) return;
      const mark=locationMark; syncSettings(); styleDocument(); await frame.contentDocument.fonts.ready; measure(); goToAnchor(mark?.anchor || "");
    },150);
  });
  syncSettings();
  const initial = saved.location && book.chapters[saved.location.chapter] ? saved.location : {chapter:0,anchor:""};
  navigate(initial.chapter, initial.anchor).catch(error => { $("loading").textContent="책을 열지 못했습니다. content 폴더를 통째로 보관했는지 확인해 주세요."; console.error(error); });
})();
