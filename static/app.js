(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const state = {
    catalog: { schools: [], heroes: [] },
    schoolMap: new Map(),
    heroMap: new Map(),
    status: null,
    draft: null,
    selectedHeroes: [],
    enabled: [],
    banned: [],
    lastResult: null,
    guideRows: [],
    guideHero: null,
    guideTemplate: "",
    toastTimer: null,
  };

  const CONFIDENCE_TEXT = { high: "高置信", medium: "中等", low: "低置信", backup: "备选" };
  const DIFFICULTY_TEXT = { 1: "简单", 2: "中等", 3: "偏难" };

  // ------------------------------------------------------------------ utils
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function toast(message, isError = false) {
    const el = $("#toast");
    el.textContent = message;
    el.className = "toast" + (isError ? " error" : "");
    el.hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => { el.hidden = true; }, 3600);
  }

  async function api(path, options = {}) {
    const opts = Object.assign({ headers: {} }, options);
    if (opts.body && typeof opts.body !== "string") {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch (e) { data = { error: "服务器返回异常" }; }
    if (!res.ok || data.ok === false) {
      throw new Error(data && data.error ? data.error : "请求失败（" + res.status + "）");
    }
    return data;
  }

  function portraitUrl(path) {
    if (!path) return "";
    if (path.startsWith("data:") || path.startsWith("http")) return path;
    return path.startsWith("/") ? path : "/" + path;
  }

  function schoolName(id) {
    const s = state.schoolMap.get(id);
    return s ? s.name : id;
  }

  function selectedNames() {
    return state.selectedHeroes.filter(Boolean);
  }

  function renderConfidence(value) {
    if (!value) return '<span class="tag">识别结果</span>';
    const label = CONFIDENCE_TEXT[value] || value;
    return '<span class="tag conf-' + escapeHtml(value) + '">' + escapeHtml(label) + "</span>";
  }

  function setLoading(text) {
    $("#emptyState").hidden = true;
    $("#resultContent").hidden = true;
    $("#loadingState").hidden = false;
    $("#loadingText").textContent = text || "处理中…";
  }

  function clearLoading() {
    $("#loadingState").hidden = true;
  }

  // ------------------------------------------------------------------- init
  async function init() {
    bindEvents();
    try {
      const [catalog, status] = await Promise.all([api("/api/catalog"), api("/api/status")]);
      state.catalog = catalog;
      state.schoolMap = new Map(catalog.schools.map((s) => [s.id, s]));
      state.heroMap = new Map(catalog.heroes.map((h) => [h.name, h]));
      state.status = status;
      updateStatus(status);
      const params = new URLSearchParams(window.location.search);
      if (params.get("open") === "guides") {
        await openGuides();
      } else if (params.get("demo") === "1" && status.sample) {
        setTimeout(loadSample, 200);
      }
    } catch (err) {
      toast(err.message, true);
    }
  }

  function updateStatus(status) {
    state.status = status;
    $("#statGuides").textContent = status.guides;
    $("#statHeroes").textContent = status.portraits + "/" + status.heroes;
    if (status.guides) $("#statGuides").title = "已收录 " + status.heroes + " 位英雄，其中 " + status.portraits + " 位有头像模板";
    $("#footerVersion").textContent = "v" + status.version;
  }

  async function refreshStatus() {
    try {
      updateStatus(await api("/api/status"));
    } catch (e) { /* silent */ }
  }

  // ----------------------------------------------------------------- upload
  function bindEvents() {
    const dropzone = $("#dropzone");
    const input = $("#fileInput");

    $("#btnPick").addEventListener("click", (e) => { e.stopPropagation(); input.click(); });
    $("#btnSample").addEventListener("click", (e) => { e.stopPropagation(); loadSample(); });
    dropzone.addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
      if (input.files && input.files[0]) handleFile(input.files[0]);
      input.value = "";
    });
    ["dragenter", "dragover"].forEach((name) => {
      dropzone.addEventListener(name, (e) => { e.preventDefault(); dropzone.classList.add("dragging"); });
    });
    ["dragleave", "drop"].forEach((name) => {
      dropzone.addEventListener(name, (e) => { e.preventDefault(); dropzone.classList.remove("dragging"); });
    });
    dropzone.addEventListener("drop", (e) => {
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) handleFile(file);
    });

    document.addEventListener("paste", (e) => {
      if (!e.clipboardData) return;
      const items = Array.from(e.clipboardData.items || []);
      const imageItem = items.find((item) => item.type && item.type.startsWith("image/"));
      if (imageItem) {
        const file = imageItem.getAsFile();
        if (file) { e.preventDefault(); handleFile(file); }
      }
    });

    $("#btnReplace").addEventListener("click", () => input.click());
    $("#btnResetDraft").addEventListener("click", () => {
      if (state.draft) applyDraft(state.draft, true);
    });
    $("#btnAnalyze").addEventListener("click", () => generate());
    $("#btnGuides").addEventListener("click", openGuides);
    $("#btnSettings").addEventListener("click", openSettings);

    $$("[data-close]").forEach((btn) => btn.addEventListener("click", () => closeModal(btn.dataset.close)));
    $$(".modal-backdrop").forEach((backdrop) => {
      backdrop.addEventListener("mousedown", (e) => {
        if (e.target === backdrop) closeModal(backdrop.id);
      });
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        $$(".modal-backdrop").forEach((m) => { if (!m.hidden) closeModal(m.id); });
      }
    });

    $("#btnSaveSettings").addEventListener("click", saveSettings);
    $("#guideSearch").addEventListener("input", renderGuideList);
    $("#btnGuideTemplate").addEventListener("click", applyGuideTemplate);
    $("#btnSaveGuide").addEventListener("click", saveGuide);
    $("#guideEditor").addEventListener("input", () => {
      $("#guideCount").textContent = $("#guideEditor").value.length + " 字";
    });
  }

  async function handleFile(file) {
    if (!file.type || !file.type.startsWith("image/")) {
      toast("请上传 PNG / JPG 图片", true);
      return;
    }
    if (file.size > 18 * 1024 * 1024) {
      toast("图片过大，请压缩后再上传", true);
      return;
    }
    const dataUrl = await readFile(file);
    setLoading("正在识别截图…");
    try {
      const result = await api("/api/analyze", { method: "POST", body: { image: dataUrl } });
      applyDraft(result);
    } catch (err) {
      clearLoading();
      $("#emptyState").hidden = false;
      toast(err.message, true);
    }
  }

  function readFile(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("读取图片失败"));
      reader.readAsDataURL(file);
    });
  }

  async function loadSample() {
    setLoading("正在识别示例截图…");
    try {
      const result = await api("/api/sample", { method: "POST", body: {} });
      applyDraft(result);
    } catch (err) {
      clearLoading();
      $("#emptyState").hidden = false;
      toast(err.message, true);
    }
  }

  // ------------------------------------------------------------------ draft
  function applyDraft(data, keepPosition = false) {
    state.draft = data;
    state.selectedHeroes = data.heroes.map((h) => h.name || "");
    state.enabled = data.schools.enabled.map((s) => s.id);
    state.banned = data.schools.banned.map((s) => s.id);
    $("#previewImg").src = data.image.preview;
    $("#previewWrap").hidden = false;
    $("#dropzone").hidden = true;
    $("#draftPanel").hidden = false;
    renderDraft();
    if (!keepPosition) {
      const ready = state.selectedHeroes.filter(Boolean).length === 3 && state.enabled.length === 8;
      if (ready) {
        setTimeout(() => { generate(true); }, 150);
      } else {
        clearLoading();
        $("#emptyState").hidden = false;
        $("#resultContent").hidden = true;
        toast("有英雄未自动识别，请在下拉框选择；修正后会自动生成推荐", true);
      }
    }
  }

  function renderDraft() {
    renderHeroes();
    renderSchools();
    const en = $("#enabledCount"); const bn = $("#bannedCount");
    en.textContent = state.enabled.length;
    bn.textContent = state.banned.length;
    const valid = state.enabled.length === 8 && state.banned.length === 5 && state.selectedHeroes.filter(Boolean).length === 3;
    $("#btnAnalyze").disabled = !valid;
    const warn = $("#draftWarn");
    const messages = [];
    if (state.enabled.length !== 8 || state.banned.length !== 5) {
      messages.push("当前启用 " + state.enabled.length + " / 禁用 " + state.banned.length + "，需要恢复为 8 / 5 才能生成推荐。");
    }
    if (state.draft && state.draft.warnings && state.draft.warnings.length) {
      messages.unshift(...state.draft.warnings);
    }
    if (state.selectedHeroes.filter(Boolean).length < 3) messages.push("请为每个位置选择英雄。");
    if (messages.length) {
      warn.textContent = messages.join("  ");
      warn.hidden = false;
    } else {
      warn.hidden = true;
    }
  }

  function renderHeroes() {
    const row = $("#heroRow");
    row.innerHTML = "";
    const heroes = state.draft ? state.draft.heroes : [];
    for (let i = 0; i < 3; i++) {
      const hero = heroes[i] || { name: "", portrait: "", confidence: 0 };
      const selected = state.selectedHeroes[i] || "";
      const card = document.createElement("div");
      card.className = "hero-card" + (selected ? "" : " unknown");
      const catalogHero = state.catalog.heroes.find((h) => h.name === selected) || state.catalog.heroes.find((h) => h.name === hero.name);
      const img = portraitUrl((catalogHero && catalogHero.art) || hero.portrait);
      const options = ['<option value="">请选择英雄</option>'];
      if (selected && !state.heroMap.has(selected)) {
        options.push('<option value="' + escapeHtml(selected) + '" selected>' + escapeHtml(selected) + "</option>");
      }
      state.catalog.heroes.forEach((h) => {
        options.push('<option value="' + escapeHtml(h.name) + '"' + (h.name === selected ? " selected" : "") + ">" + escapeHtml(h.name) + "</option>");
      });
      options.push('<option value="__custom__">＋ 输入新英雄</option>');
      const conf = hero.confidence ? Math.round(hero.confidence * 100) + "%" : "待确认";
      card.innerHTML =
        '<div class="portrait">' +
          (img ? '<img src="' + img + '" alt="">' : "") +
          '<span class="rank">' + (i + 1) + "</span>" +
          '<span class="conf">' + conf + "</span>" +
        "</div>" +
        '<select data-slot="' + i + '">' + options.join("") + "</select>";
      const select = $("select", card);
      select.addEventListener("change", () => onHeroChange(i, select.value));
      row.appendChild(card);
    }
  }

  async function onHeroChange(slot, value) {
    if (value === "__custom__") {
      const name = window.prompt("输入英雄名称（会保存头像模板，下次自动识别）");
      if (!name || !name.trim()) { renderHeroes(); return; }
      value = name.trim();
      if (!state.heroMap.has(value)) {
        state.catalog.heroes.push({ name: value, tier: "?", role: "未收录", portrait: "", art: "", has_guide: false });
        state.heroMap.set(value, state.catalog.heroes[state.catalog.heroes.length - 1]);
      }
    }
    state.selectedHeroes[slot] = value;
    if (state.draft && state.draft.heroes[slot]) state.draft.heroes[slot].name = value;
    renderDraft();
    const ready = state.selectedHeroes.filter(Boolean).length === 3 && state.enabled.length === 8 && state.banned.length === 5;
    if (ready && value) {
      clearTimeout(state.autoRecommendTimer);
      state.autoRecommendTimer = setTimeout(() => generate(true), 350);
    }
    if (value && state.draft && state.draft.heroes[slot] && state.draft.heroes[slot].portrait) {
      try {
        await api("/api/learn-hero", {
          method: "POST",
          body: { name: value, portrait: state.draft.heroes[slot].portrait },
        });
        toast("已记住 " + value + " 的头像，下次可自动识别");
        refreshStatus();
      } catch (err) {
        toast("头像学习失败：" + err.message, true);
      }
    }
  }

  function renderSchools() {
    const enabled = $("#enabledChips");
    const banned = $("#bannedChips");
    enabled.innerHTML = "";
    banned.innerHTML = "";
    state.enabled.forEach((id) => enabled.appendChild(schoolChip(id, true)));
    state.banned.forEach((id) => banned.appendChild(schoolChip(id, false)));
    if (!state.enabled.length) enabled.innerHTML = '<span class="tiny-note">暂无启用流派</span>';
    if (!state.banned.length) banned.innerHTML = '<span class="tiny-note">暂无禁用流派</span>';
  }

  function schoolChip(id, isEnabled) {
    const school = state.schoolMap.get(id) || { name: id, icon: "" };
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip" + (isEnabled ? "" : " banned");
    chip.title = school.summary || "";
    chip.innerHTML =
      (school.icon ? '<img src="' + escapeHtml(school.icon) + '" alt="">' : "") +
      '<i class="dot"></i><span class="name">' + escapeHtml(school.name) + "</span>";
    chip.addEventListener("click", () => toggleSchool(id));
    return chip;
  }

  function toggleSchool(id) {
    if (state.enabled.includes(id)) {
      state.enabled = state.enabled.filter((x) => x !== id);
      state.banned.push(id);
    } else if (state.banned.includes(id)) {
      state.banned = state.banned.filter((x) => x !== id);
      state.enabled.push(id);
    } else {
      state.enabled.push(id);
    }
    renderDraft();
  }

  // --------------------------------------------------------------- recommend
  async function generate(silent = false) {
    if (!silent) setLoading("正在检索攻略并评分…");
    try {
      const result = await api("/api/recommend", {
        method: "POST",
        body: { heroes: selectedNames(), enabled: state.enabled, banned: state.banned },
      });
      renderResult(result, { scroll: !silent });
    } catch (err) {
      clearLoading();
      $("#emptyState").hidden = false;
      toast(err.message, true);
    }
  }

  function renderResult(result, options = {}) {
    state.lastResult = result;
    clearLoading();
    $("#emptyState").hidden = true;
    $("#resultContent").hidden = false;
    const top = result.recommendations[0];
    const verdict = $("#verdictCard");
    if (!top) {
      verdict.innerHTML = '<p class="verdict-text">没有可推荐的英雄。</p>';
      $("#cards").innerHTML = "";
      return;
    }
    const portrait = portraitUrl(top.art || top.portrait);
    const conf = CONFIDENCE_TEXT[top.confidence] || top.confidence;
    const mainSchools = (top.build.schools || []).slice(0, 2).join(" + ");
    verdict.innerHTML =
      '<div class="verdict-top">' +
        (portrait ? '<img class="verdict-portrait" src="' + portrait + '" alt="">' : "") +
        '<div class="verdict-copy">' +
          '<div class="verdict-label">本局首选</div>' +
          '<div class="verdict-name">' + escapeHtml(top.name) +
            '<span class="tier">' + escapeHtml(top.tier || "?") + " 级</span>" +
          "</div>" +
          '<div class="verdict-sub">' + escapeHtml(top.role || "") + " · 难度 " + escapeHtml(DIFFICULTY_TEXT[top.difficulty] || "中等") +
            (mainSchools ? " · 路线 " + escapeHtml(mainSchools) : "") +
          "</div>" +
        "</div>" +
        '<div class="score-badge"><b>' + escapeHtml(top.score) + "</b><span>RECOMMEND</span></div>" +
      "</div>" +
      '<p class="verdict-text">' + escapeHtml(result.verdict) + "</p>" +
      '<div class="verdict-tags">' +
        '<span class="tag conf-' + escapeHtml(top.confidence) + '">' + escapeHtml(conf) + "</span>" +
        '<span class="tag">' + escapeHtml(top.tier || "?") + " 级强度</span>" +
        '<span class="tag">' + (top.has_guide ? "攻略已入库" : "暂无完整攻略") + "</span>" +
        '<span class="tag">领先 ' + escapeHtml(result.margin) + " 分</span>" +
      "</div>" +
      '<div class="verdict-actions">' +
        '<button class="btn ghost small" id="btnCopy">复制结论</button>' +
        '<button class="btn ghost small" id="btnAI">AI 点评</button>' +
      "</div>" +
      '<div id="aiBox" class="ai-box" hidden></div>';

    $("#btnCopy").addEventListener("click", copyConclusion);
    $("#btnAI").addEventListener("click", requestAI);

    const envList = $("#envNotes");
    envList.innerHTML = (result.environment.notes || [])
      .map((note) => "<li>" + escapeHtml(note) + "</li>").join("");

    const cards = $("#cards");
    cards.innerHTML = "";
    result.recommendations.forEach((card, index) => {
      cards.appendChild(buildCard(card, index));
    });
    if (options.scroll) {
      $("#resultPanel").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function meter(label, value) {
    const v = Math.max(0, Math.min(100, Number(value) || 0));
    return (
      '<div class="meter"><div class="m-label"><span>' + label + "</span><b>" + Math.round(v) + "</b></div>" +
      '<div class="track"><div class="fill" style="width:' + v + '%"></div></div></div>'
    );
  }

  function buildCard(card, index) {
    const el = document.createElement("article");
    el.className = "rec-card" + (index === 0 ? " top" : "");
    el.style.animationDelay = Math.min(index * 0.05, 0.2) + "s";
    const portrait = portraitUrl(card.art || card.portrait);
    const b = card.breakdown || {};
    const reasons = (card.reasons || []).map((r) => "<li>" + escapeHtml(r) + "</li>").join("");
    const steps = (card.build && card.build.steps ? card.build.steps : []).map((s) => "<li>" + escapeHtml(s) + "</li>").join("");
    const risks = (card.risks || []).slice(0, 3).map((r) => escapeHtml(r)).join("；");
    const corePlan = (card.core_cards || []).map((c) => {
      const rcls = Number(c.rarity) >= 3 ? "r3" : Number(c.rarity) === 2 ? "r2" : "r1";
      const factions = (c.factions || []).map((f) => '<span class="pc-school">' + escapeHtml(f) + "</span>").join("");
      return (
        '<div class="plan-card">' +
          '<div class="pc-head"><span class="pc-name">' + escapeHtml(c.name) + "</span>" +
            '<span class="pc-rarity ' + rcls + '">' + escapeHtml(c.rarity_name || "") + "</span></div>" +
          '<div class="pc-schools">' + factions + (c.reason ? '<span class="pc-reason">' + escapeHtml(c.reason) + "</span>" : "") + "</div>" +
          '<div class="pc-desc">' + escapeHtml(c.desc || "") + "</div>" +
        "</div>"
      );
    }).join("");
    const evidence = (card.evidence || []).map((ev) =>
      '<div class="evidence-item">' +
        '<div class="ev-head"><span>' + escapeHtml(ev.section || "攻略摘录") + (ev.same_hero === false ? " · 其他英雄" : "") + "</span><span>BM25 " + escapeHtml(ev.score) + "</span></div>" +
        "<p>" + escapeHtml(ev.text) + "</p>" +
        (ev.source ? '<div class="ev-src">来源：' + escapeHtml(ev.source) + "</div>" : "") +
      "</div>"
    ).join("");
    const skillIcons =
      (card.talent_icon ? '<img class="rec-skill" src="' + portraitUrl(card.talent_icon) + '" title="天赋" alt="">' : "") +
      (card.ultimate_icon ? '<img class="rec-skill" src="' + portraitUrl(card.ultimate_icon) + '" title="大招" alt="">' : "");
    el.innerHTML =
      '<div class="rec-head">' +
        (portrait ? '<img class="rec-portrait" src="' + portrait + '" alt="">' : "") +
        '<div class="rec-name">' +
          "<h3>" + escapeHtml(card.name) +
            '<span class="tag">' + escapeHtml(card.tier || "?") + " 级</span>" +
            (index === 0 ? '<span class="tag" style="color:#f2d18c;border-color:rgba(231,189,97,.3);background:rgba(231,189,97,.08)">首选</span>' : "") +
          "</h3>" +
          "<p>" + escapeHtml(card.role || "") + " · " + (card.has_guide ? "有攻略" : "暂无攻略") + skillIcons + "</p>" +
        "</div>" +
        '<div class="rec-score"><b>' + escapeHtml(card.score) + "</b><span>" + escapeHtml(CONFIDENCE_TEXT[card.confidence] || "备选") + "</span></div>" +
      "</div>" +
      '<div class="meters">' +
        meter("基础强度", b.base) + meter("流派契合", b.synergy) +
        meter("本局环境", b.environment) + meter("版本数据", b.meta) +
      "</div>" +
      (reasons ? '<ul class="rec-reasons">' + reasons + "</ul>" : "") +
      (corePlan ? '<div class="plan-box"><div class="build-title">核心卡 · 优先围绕主系抓取</div><div class="plan-cards">' + corePlan + "</div></div>" : "") +
      (steps ? '<div class="build-box"><div class="build-title">开局路线</div><ol class="build-steps">' + steps + "</ol></div>" : "") +
      (risks ? '<div class="risk-row"><span class="risk-label">注意</span><span class="risk-text">' + risks + "</span></div>" : "") +
      (evidence ? '<details class="evidence"><summary>攻略依据（' + (card.evidence || []).length + " 段）</summary><div class=\"evidence-list\">" + evidence + "</div></details>" : "");
    return el;
  }

  function copyConclusion() {
    if (!state.lastResult) return;
    const r = state.lastResult;
    const top = r.recommendations[0];
    const lines = [
      "选技大乱斗 · 开局推荐",
      "启用：" + r.draft.enabled.map((s) => s.name).join("、"),
      "禁用：" + r.draft.banned.map((s) => s.name).join("、"),
      "候选：" + r.draft.heroes.join(" / "),
      "首选：" + top.name + "（" + top.score + " 分）",
      "理由：" + (top.reasons || []).slice(0, 3).join(" "),
      "路线：" + (top.build.steps || []).join(" → "),
    ];
    const text = lines.join("\n");
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => toast("结论已复制")).catch(() => toast("复制失败", true));
    } else {
      toast("当前浏览器不支持自动复制", true);
    }
  }

  async function requestAI() {
    if (!state.lastResult) return;
    if (!state.status || !state.status.llm || !state.status.llm.enabled) {
      toast("请先在设置中启用 AI 点评");
      openSettings();
      return;
    }
    const btn = $("#btnAI");
    const box = $("#aiBox");
    btn.disabled = true;
    btn.textContent = "生成中…";
    box.hidden = false;
    box.textContent = "正在基于攻略摘录生成点评…";
    try {
      const data = await api("/api/comment", {
        method: "POST",
        body: {
          heroes: state.selectedHeroes,
          enabled: state.enabled,
          banned: state.banned,
        },
      });
      box.textContent = data.comment;
    } catch (err) {
      box.textContent = "AI 点评失败：" + err.message;
      toast(err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "AI 点评";
    }
  }

  // ---------------------------------------------------------------- settings
  async function openSettings() {
    openModal("settingsModal");
    try {
      const data = await api("/api/settings");
      const llm = data.llm;
      $("#llmEnabled").checked = !!llm.enabled;
      $("#llmBase").value = llm.base_url || "";
      $("#llmModel").value = llm.model || "";
      $("#llmKey").value = "";
      $("#llmKeyHint").textContent = llm.api_key_set
        ? "已配置（" + llm.api_key_masked + "）。留空表示保持不变。"
        : "尚未配置。Key 只保存在本机 data/settings.json。";
    } catch (err) {
      toast(err.message, true);
    }
  }

  async function saveSettings() {
    const enabled = $("#llmEnabled").checked;
    const baseUrl = $("#llmBase").value.trim();
    const model = $("#llmModel").value.trim();
    const key = $("#llmKey").value.trim();
    if (enabled && !key && !(state.status && state.status.llm && state.status.llm.key_set)) {
      toast("启用 AI 点评前请先填写 API Key", true);
      return;
    }
    try {
      await api("/api/settings", {
        method: "POST",
        body: { llm: { enabled, base_url: baseUrl, model, api_key: key } },
      });
      closeModal("settingsModal");
      toast("设置已保存");
      refreshStatus();
    } catch (err) {
      toast(err.message, true);
    }
  }

  // ------------------------------------------------------------------ guides
  async function openGuides() {
    openModal("guidesModal");
    $("#guideSaveTip").textContent = "";
    await loadGuideRows();
    if (state.guideRows.length && !state.guideHero) {
      const first = state.guideRows.find((row) => row.has_guide) || state.guideRows[0];
      selectGuideHero(first.name);
    }
  }

  async function loadGuideRows() {
    try {
      const data = await api("/api/guides");
      state.guideRows = data.heroes || [];
      state.guideTemplate = data.template || "";
      renderGuideList();
    } catch (err) {
      toast(err.message, true);
    }
  }

  function renderGuideList() {
    const query = ($("#guideSearch").value || "").trim().toLowerCase();
    const list = $("#guideList");
    list.innerHTML = "";
    state.guideRows
      .filter((row) => !query || row.name.toLowerCase().includes(query))
      .forEach((row) => {
        const meta = state.heroMap.get(row.name);
        const div = document.createElement("div");
        div.className = "guide-row" + (row.has_guide ? " has-guide" : "") + (state.guideHero === row.name ? " active" : "");
        const portrait = meta && (meta.art || meta.portrait) ? portraitUrl(meta.art || meta.portrait) : "";
        div.innerHTML =
          (portrait ? '<img class="gi" src="' + portrait + '" alt="">' : '<span class="gi" style="display:grid;place-items:center;color:#8fa0b5">' + escapeHtml(row.name.slice(0, 1)) + "</span>") +
          '<span class="gn">' + escapeHtml(row.name) + "</span>" +
          '<span class="tier">' + escapeHtml(row.tier || "") + "</span>" +
          '<i class="gd"></i>';
        div.addEventListener("click", () => selectGuideHero(row.name));
        list.appendChild(div);
      });
    if (!list.children.length) list.innerHTML = '<p class="tiny-note" style="padding:10px">没有匹配的英雄</p>';
  }

  async function selectGuideHero(name) {
    state.guideHero = name;
    renderGuideList();
    $("#guideHeroName").textContent = name;
    $("#guideSaveTip").textContent = "";
    const row = state.guideRows.find((r) => r.name === name);
    $("#guideMeta").textContent = row && row.has_guide
      ? "已收录 " + row.sections + " 段 · " + row.updated
      : "尚未收录攻略，点击「插入模板」开始写。";
    try {
      const data = await api("/api/guide?hero=" + encodeURIComponent(name));
      $("#guideEditor").value = data.content || "";
      $("#guideCount").textContent = $("#guideEditor").value.length + " 字";
    } catch (err) {
      toast(err.message, true);
    }
  }

  function applyGuideTemplate() {
    if (!state.guideHero) { toast("请先在左侧选择英雄", true); return; }
    let template = state.guideTemplate || "";
    template = template.replace(/英雄名/g, state.guideHero);
    const current = $("#guideEditor").value.trim();
    if (current && !window.confirm("编辑框里已有内容，插入模板会覆盖，继续吗？")) return;
    $("#guideEditor").value = template;
    $("#guideCount").textContent = template.length + " 字";
    $("#guideSaveTip").textContent = "模板已插入，记得保存";
  }

  async function saveGuide() {
    if (!state.guideHero) { toast("请先选择英雄", true); return; }
    const content = $("#guideEditor").value;
    if (!content.trim()) { toast("攻略内容不能为空", true); return; }
    const btn = $("#btnSaveGuide");
    btn.disabled = true;
    try {
      const data = await api("/api/guide", {
        method: "POST",
        body: { hero: state.guideHero, content },
      });
      toast("已保存《" + data.title + "》，检索索引已重建");
      $("#guideSaveTip").textContent = "已保存";
      await loadGuideRows();
      refreshStatus();
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false;
    }
  }

  // ------------------------------------------------------------------ modals
  function openModal(id) {
    const el = $("#" + id);
    el.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeModal(id) {
    const el = $("#" + id);
    if (el) el.hidden = true;
    document.body.style.overflow = "";
  }

  // --------------------------------------------------------------------- go
  init();
})();
