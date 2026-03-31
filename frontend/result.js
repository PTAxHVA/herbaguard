document.addEventListener("DOMContentLoaded", function () {
    const STORAGE_KEY = "herbaguard:lastResult";
    const CHAT_SEED_KEY = "herbaguard:chatSeed";

    const alertCard = document.getElementById("alertCard");
    const alertIcon = document.getElementById("alertIcon");
    const alertTitle = document.getElementById("alertTitle");
    const alertMessage = document.getElementById("alertMessage");
    const alertRecommendation = document.getElementById("alertRecommendation");

    const resolvedList = document.getElementById("resolvedList");
    const unresolvedBox = document.getElementById("unresolvedBox");
    const unresolvedList = document.getElementById("unresolvedList");
    const pairContainer = document.getElementById("pairContainer");
    const safeState = document.getElementById("safeState");

    const btnRecheck = document.getElementById("btnRecheck");
    const btnShare = document.getElementById("btnShare");
    const btnShareTop = document.getElementById("btnShareTop");
    const btnExportPdf = document.getElementById("btnExportPdf");
    const btnAskChat = document.getElementById("btnAskChat");

    let payload = null;

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function toTypeLabel(type) {
        return type === "drug" ? "Thuốc Tây" : "Thảo Dược";
    }

    function toSeverityLabel(severity) {
        return severity === "high" ? "Cảnh báo cao" : "Cần theo dõi";
    }

    function renderBanner(summary) {
        const level = (summary && summary.level) || "safe";
        const title = (summary && summary.title) || "KẾT QUẢ PHÂN TÍCH";
        const message = (summary && summary.message) || "Chưa có dữ liệu.";
        const recommendation = (summary && summary.recommendation) || "";

        alertCard.classList.remove("danger", "warning", "safe");
        alertCard.classList.add(level);

        if (level === "danger") {
            alertIcon.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
        } else if (level === "warning") {
            alertIcon.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i>';
        } else {
            alertIcon.innerHTML = '<i class="fa-solid fa-circle-check"></i>';
        }

        alertTitle.textContent = title;
        alertMessage.textContent = message;
        alertRecommendation.textContent = recommendation;

        if (window.HerbaGuardApp && typeof window.HerbaGuardApp.speakText === "function") {
            window.HerbaGuardApp.speakText(`${title}. ${message}`);
        }
    }

    function renderResolvedItems(items) {
        if (!items || items.length === 0) {
            resolvedList.innerHTML = '<div class="empty-placeholder">Không có mục nào được nhận diện.</div>';
            return;
        }

        resolvedList.innerHTML = items
            .map((item) => {
                const confidence = typeof item.confidence === "number" ? Math.round(item.confidence * 100) : 0;
                const iconColor = item.type === "drug" ? "blue" : "green";
                const iconClass = item.type === "drug" ? "fa-capsules" : "fa-leaf";
                return `
                    <div class="medicine-card">
                        <div class="card-left">
                            <div class="icon-box ${iconColor}">
                                <i class="fa-solid ${iconClass}"></i>
                            </div>
                            <div class="card-info">
                                <h4>${escapeHtml(item.canonical_name || "")}</h4>
                                <p>Nhập: ${escapeHtml(item.input || "")} • Khớp: ${escapeHtml(item.matched_alias || "")}</p>
                            </div>
                        </div>
                        <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 6px;">
                            <span class="type-badge ${item.type}">${toTypeLabel(item.type)}</span>
                            <span style="font-size: 12px; color: var(--slate-500);">Độ khớp ${confidence}%</span>
                        </div>
                    </div>
                `;
            })
            .join("");
    }

    function renderUnresolvedItems(items) {
        if (!items || items.length === 0) {
            unresolvedBox.classList.add("hidden");
            unresolvedList.innerHTML = "";
            return;
        }

        unresolvedBox.classList.remove("hidden");
        unresolvedList.innerHTML = items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    }

    function renderPairs(pairs) {
        if (!pairs || pairs.length === 0) {
            pairContainer.innerHTML = "";
            safeState.classList.remove("hidden");
            return;
        }

        safeState.classList.add("hidden");
        pairContainer.innerHTML = pairs
            .map((pair) => {
                const consequences = (pair.interaction && pair.interaction.possible_consequences) || [];
                const consequenceHtml = consequences.length
                    ? consequences.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
                    : "<li>Không có dữ liệu hậu quả bổ sung trong cơ sở dữ liệu.</li>";

                return `
                    <div class="details-box">
                        <div class="pair-header">
                            <h3>${escapeHtml(pair.drug.canonical_name)} + ${escapeHtml(pair.herb.canonical_name)}</h3>
                            <span class="severity-tag ${pair.severity}">${toSeverityLabel(pair.severity)}</span>
                        </div>
                        <p><strong>Cơ chế:</strong> ${escapeHtml(pair.interaction.mechanism || "")}</p>
                        <p style="margin-top: 10px;"><strong>Hậu quả có thể gặp:</strong></p>
                        <ul class="bullet-list">${consequenceHtml}</ul>
                        <p style="margin-top: 10px;"><strong>Khuyến nghị:</strong> ${escapeHtml(pair.interaction.recommendation || "")}</p>
                    </div>
                `;
            })
            .join("");
    }

    function renderFallback() {
        renderBanner({
            level: "warning",
            title: "KHÔNG TÌM THẤY KẾT QUẢ",
            message: "Không có dữ liệu phân tích trong phiên làm việc hiện tại.",
            recommendation: "Vui lòng quay lại trang kiểm tra và thực hiện lại.",
        });
        renderResolvedItems([]);
        renderUnresolvedItems([]);
        renderPairs([]);
    }

    function buildShareText() {
        if (!payload) {
            return "HerbaGuard: chưa có dữ liệu kết quả trong phiên hiện tại.";
        }

        const lines = [];
        lines.push(`HerbaGuard - ${payload.summary && payload.summary.title ? payload.summary.title : "Kết quả kiểm tra"}`);
        lines.push(payload.summary && payload.summary.message ? payload.summary.message : "");

        const pairs = payload.interaction_pairs || [];
        if (pairs.length > 0) {
            lines.push("Các cặp tương tác:");
            pairs.slice(0, 5).forEach((pair) => {
                lines.push(`- ${pair.drug.canonical_name} + ${pair.herb.canonical_name} (${pair.severity === "high" ? "cao" : "theo dõi"})`);
            });
        } else {
            lines.push("Chưa ghi nhận tương tác trong dữ liệu local.");
        }

        const unresolved = payload.unresolved_items || [];
        if (unresolved.length > 0) {
            lines.push(`Mục chưa nhận diện: ${unresolved.join(", ")}`);
        }

        lines.push("Nguồn: database/herb.json, database/drug.json, database/interaction.json");

        return lines.filter(Boolean).join("\n");
    }

    async function copyToClipboard(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
            return true;
        }

        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "true");
        textarea.style.position = "fixed";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        const success = document.execCommand("copy");
        document.body.removeChild(textarea);
        return success;
    }

    async function shareResult() {
        const text = buildShareText();
        const shareData = {
            title: "HerbaGuard - Kết quả kiểm tra",
            text: text,
            url: window.location.href,
        };

        if (navigator.share) {
            try {
                await navigator.share(shareData);
                return;
            } catch (error) {
                // Fall through clipboard copy.
            }
        }

        try {
            await copyToClipboard(text);
            alert("Đã sao chép nội dung kết quả vào clipboard.");
        } catch (error) {
            alert("Không thể chia sẻ lúc này. Vui lòng thử lại.");
        }
    }

    function exportPdf() {
        window.print();
    }

    function askChatFromResult() {
        if (!payload) {
            window.location.href = "chat.html";
            return;
        }

        const pairs = payload.interaction_pairs || [];
        let prompt = "Tôi vừa kiểm tra tương tác. Bạn giải thích thêm giúp tôi.";
        if (pairs.length > 0) {
            const first = pairs[0];
            prompt = `Tôi vừa kiểm tra cặp ${first.drug.canonical_name} và ${first.herb.canonical_name}. Tại sao nguy hiểm và tôi nên làm gì?`;
        } else if ((payload.resolved_items || []).length >= 2) {
            const names = payload.resolved_items.slice(0, 3).map((item) => item.canonical_name).join(" và ");
            prompt = `Tôi vừa kiểm tra ${names}. Vì sao chưa có tương tác và tôi cần lưu ý gì?`;
        }

        sessionStorage.setItem(
            CHAT_SEED_KEY,
            JSON.stringify({
                prompt: prompt,
                created_at: new Date().toISOString(),
                from: "result",
            })
        );

        window.location.href = "chat.html";
    }

    try {
        const raw = sessionStorage.getItem(STORAGE_KEY);
        payload = raw ? JSON.parse(raw) : null;
    } catch (error) {
        payload = null;
    }

    if (!payload) {
        renderFallback();
    } else {
        renderBanner(payload.summary || {});
        renderResolvedItems(payload.resolved_items || []);
        renderUnresolvedItems(payload.unresolved_items || []);
        renderPairs(payload.interaction_pairs || []);
    }

    if (btnRecheck) {
        btnRecheck.addEventListener("click", function () {
            window.location.href = "check.html";
        });
    }

    if (btnShare) {
        btnShare.addEventListener("click", shareResult);
    }

    if (btnShareTop) {
        btnShareTop.addEventListener("click", shareResult);
    }

    if (btnExportPdf) {
        btnExportPdf.addEventListener("click", exportPdf);
    }

    if (btnAskChat) {
        btnAskChat.addEventListener("click", askChatFromResult);
    }
});
