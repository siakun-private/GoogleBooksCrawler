/* 생성 페이지의 목차와 페이지 목록을 실제로 조작해 화면 안에 도달하는지 검사한다. */
(async () => {
  const $ = id => document.getElementById(id);
  const book = JSON.parse($("book-data").textContent);
  const frame = $("book-frame");
  const failures = [], images = new Set(), external = new Set();
  const testedChapters = new Set();
  let footnote;
  const wait = async predicate => {
    for (let n = 0; n < 300; n++) {
      if (predicate()) return;
      await new Promise(resolve => setTimeout(resolve, 30));
    }
    throw new Error("Reader navigation did not settle");
  };
  const ready = chapter => document.body.dataset.ready === "true" && Number(document.body.dataset.chapter) === chapter;
  const inspect = (entry, label) => {
    const doc = frame.contentDocument;
    const rect = doc.getElementById(entry.anchor)?.getBoundingClientRect();
    const area = doc.getElementById("reading-window").getBoundingClientRect();
    if (entry.anchor && (!rect || rect.left < area.left-3 || rect.left > area.right+3)) failures.push({target:label,problem:"Anchor is outside the visible screen"});
    if (testedChapters.has(entry.chapter)) return;
    testedChapters.add(entry.chapter);
    for (const image of doc.images) {
      if (!image.complete || !image.naturalWidth) failures.push({target:label,problem:"Image did not load",src:image.getAttribute("src")});
      images.add(image.src);
    }
    for (const resource of doc.defaultView.performance.getEntriesByType("resource")) if (/^https?:/.test(resource.name)) external.add(resource.name);
    if (!footnote) {
      const link = [...doc.querySelectorAll("a[href]")].find(a => a.getAttribute("epub:type") === "noteref");
      if (link) footnote = {chapter:entry.chapter,href:link.getAttribute("href")};
    }
  };
  const jumpPage = async index => {
    $("page-number").value = String(index+1);
    $("page-form").requestSubmit();
    await wait(() => ready(book.pages[index].chapter));
  };
  for (let index = 0; index < book.pages.length; index++) {
    await jumpPage(index);
    inspect(book.pages[index], book.pages[index].label);
    if (index+1 < Number(document.body.dataset.pageStart) || index+1 > Number(document.body.dataset.pageEnd)) failures.push({target:book.pages[index].label,problem:"Selected page is outside displayed range"});
  }
  for (let index = 0; index < book.toc.length; index++) {
    $("toc-list").children[index].click();
    await wait(() => ready(book.toc[index].chapter));
    inspect(book.toc[index], book.toc[index].label);
  }
  let footnoteResult = "not present";
  if (footnote) {
    const sourcePage = book.pages.findIndex(p => p.chapter === footnote.chapter);
    if (sourcePage >= 0) {
      await jumpPage(sourcePage);
      const sourceURL = new URL(book.chapters[footnote.chapter].file, location.href);
      const targetURL = new URL(footnote.href, sourceURL);
      const targetChapter = book.chapters.findIndex(c => new URL(c.file, location.href).pathname === targetURL.pathname);
      const link = [...frame.contentDocument.querySelectorAll("a[href]")].find(a => a.getAttribute("href") === footnote.href);
      link.click();
      await wait(() => ready(targetChapter));
      inspect({chapter:targetChapter,anchor:decodeURIComponent(targetURL.hash.slice(1))}, "footnote");
      const backlink = [...frame.contentDocument.querySelectorAll("a[href]")].find(a => new URL(a.getAttribute("href"),targetURL).pathname === sourceURL.pathname);
      if (backlink) {
        backlink.click(); await wait(() => ready(footnote.chapter)); footnoteResult = "round trip passed";
      } else {
        footnoteResult = "destination passed; no backlink present";
      }
    }
  }
  $("settings-toggle").click();
  const theme = document.documentElement.dataset.theme;
  $("dark-theme").click();
  if (document.documentElement.dataset.theme === theme || frame.contentDocument.documentElement.dataset.theme !== document.documentElement.dataset.theme) failures.push({problem:"Theme did not apply to controls and content"});
  $("dark-theme").click();
  for (const resource of performance.getEntriesByType("resource")) if (/^https?:/.test(resource.name)) external.add(resource.name);
  if (external.size) failures.push({problem:"External reading dependency",resources:[...external]});
  return {pages:book.pages.length,toc:book.toc.length,chapters:testedChapters.size,inline_images:images.size,footnote:footnoteResult,external_resources:external.size,failures};
})()
