document.addEventListener("DOMContentLoaded", async function () {
    const api = window.HerbaGuardAPI;
    if (!api) {
        return;
    }

    const CHAT_STORAGE_PREFIX = "herbaguard:chatHistory:";
    const CHAT_SEED_KEY = "herbaguard:chatSeed";

    const chatLog = document.getElementById("chatLog");
    const chatForm = document.getElementById("chatForm");
    const chatInput = document.getElementById("chatInput");
    const btnSendChat = document.getElementById("btnSendChat");
    const typingIndicator = document.getElementById("typingIndicator");
    const quickQuestionRow = document.getElementById("quickQuestionRow");
    const btnClearChat = document.getElementById("btnClearChat");

    const state = {
        sessionId: "",
        messages: [],
        sending: false,
    };

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatTime(dateValue) {
        if (!dateValue) {
            return nowLabel();
        }
        const parsed = new Date(dateValue);
        if (Number.isNaN(parsed.getTime())) {
            return nowLabel();
        }
        return parsed.toLocaleTimeString("vi-VN", {
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function nowLabel() {
        const d = new Date();
        return d.toLocaleTimeString("vi-VN", {
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function getCacheKey() {
        if (!state.sessionId) {
            return `${CHAT_STORAGE_PREFIX}default`;
        }
        return `${CHAT_STORAGE_PREFIX}${state.sessionId}`;
    }

    function saveHistoryCache() {
        try {
            sessionStorage.setItem(getCacheKey(), JSON.stringify(state.messages.slice(-80)));
        } catch (error) {
            // Ignore storage failures.
        }
    }

    function loadHistoryCache() {
        try {
            const raw = sessionStorage.getItem(getCacheKey());
            if (!raw) {
                return [];
            }
            const parsed = JSON.parse(raw);
            if (!Array.isArray(parsed)) {
                return [];
            }
            return parsed.filter((item) => item && typeof item.role === "string" && typeof item.content === "string");
        } catch (error) {
            return [];
        }
    }

    function setSending(isSending) {
        state.sending = isSending;
        if (btnSendChat) {
            btnSendChat.disabled = isSending;
        }
        if (chatInput) {
            chatInput.disabled = isSending;
        }
        if (typingIndicator) {
            typingIndicator.classList.toggle("hidden", !isSending);
        }
    }

    function buildEvidenceHtml(message) {
        const grounding = message.grounding || {};
        const entities = Array.isArray(grounding.entities) ? grounding.entities : [];
        const interactions = Array.isArray(grounding.interactions) ? grounding.interactions : [];
        const citations = Array.isArray(message.citations) ? message.citations : [];

        if (entities.length === 0 && interactions.length === 0 && citations.length === 0) {
            return "";
        }

        const entityHtml = entities.length
            ? `
                <div class="evidence-title">Thực thể nhận diện</div>
                <div class="evidence-tag-wrap">
                    ${entities
                        .map(
                            (item) =>
                                `<span class="evidence-tag ${escapeHtml(item.type)}">${escapeHtml(item.name)} (${item.type === "drug" ? "Thuốc Tây" : "Thảo Dược"})</span>`
                        )
                        .join("")}
                </div>
              `
            : "";

        const interactionHtml = interactions.length
            ? `
                <div class="evidence-title" style="margin-top: 8px;">Bằng chứng tương tác</div>
                ${interactions
                    .slice(0, 3)
                    .map((item) => {
                        const consequences = Array.isArray(item.possible_consequences) ? item.possible_consequences : [];
                        return `
                            <div class="evidence-item">
                                <strong>${escapeHtml(item.drug_name || `drug_id=${item.drug_id}`)} + ${escapeHtml(item.herb_name || `herb_id=${item.herb_id}`)} • mức ${item.severity === "high" ? "cao" : "theo dõi"}</strong>
                                <div><em>Cơ chế:</em> ${escapeHtml(item.mechanism || "")}</div>
                                <div><em>Hậu quả:</em> ${escapeHtml(consequences.join("; ") || "Không có")}</div>
                                <div><em>Khuyến nghị:</em> ${escapeHtml(item.recommendation || "")}</div>
                            </div>
                        `;
                    })
                    .join("")}
              `
            : "";

        const citationHtml = citations.length
            ? `<div class="citation-list">Nguồn: ${citations.map((item) => escapeHtml(item)).join(" • ")}</div>`
            : "";

        return `<div class="evidence-box">${entityHtml}${interactionHtml}${citationHtml}</div>`;
    }

    function renderMessages() {
        if (!chatLog) {
            return;
        }

        if (state.messages.length === 0) {
            chatLog.innerHTML = `
                <div class="empty-state">
                    Bắt đầu bằng câu hỏi như: "Nhân sâm có tương tác với warfarin không?"
                </div>
            `;
            return;
        }

        chatLog.innerHTML = state.messages
            .map((message) => {
                const evidenceHtml = message.role === "assistant" ? buildEvidenceHtml(message) : "";
                return `
                    <div class="chat-message ${escapeHtml(message.role)}">
                        <div class="chat-bubble">
                            ${escapeHtml(message.content)}
                            ${evidenceHtml}
                            <div class="chat-meta">${escapeHtml(message.time || "")}</div>
                        </div>
                    </div>
                `;
            })
            .join("");

        chatLog.scrollTop = chatLog.scrollHeight;
    }

    function appendMessage(payload) {
        state.messages.push(payload);
        saveHistoryCache();
        renderMessages();
    }

    function toApiHistory() {
        return state.messages
            .filter((item) => item.role === "user" || item.role === "assistant")
            .slice(-20)
            .map((item) => ({ role: item.role, content: item.content }));
    }

    function normalizeServerMessage(item) {
        return {
            role: item.role === "assistant" ? "assistant" : "user",
            content: String(item.content || ""),
            time: formatTime(item.created_at),
            grounding: item.grounding || {},
            citations: Array.isArray(item.citations) ? item.citations : [],
            fallback: typeof item.fallback === "boolean" ? item.fallback : false,
        };
    }

    async function hydrateHistory() {
        if (!state.sessionId) {
            state.messages = [];
            return;
        }

        try {
            const payload = await api.getChatHistory(state.sessionId, 120);
            const serverSession = String(payload.session_id || "").trim();
            if (serverSession && serverSession !== state.sessionId) {
                state.sessionId = api.setChatSessionId(serverSession) || serverSession;
            }
            const rows = Array.isArray(payload.messages) ? payload.messages : [];
            state.messages = rows.map(normalizeServerMessage);
            saveHistoryCache();
        } catch (error) {
            state.messages = loadHistoryCache();
        }
    }

    async function sendMessage(rawText) {
        const text = String(rawText || "").trim();
        if (!text || state.sending) {
            return;
        }

        appendMessage({
            role: "user",
            content: text,
            time: nowLabel(),
        });

        if (chatInput) {
            chatInput.value = "";
        }

        setSending(true);

        try {
            const response = await api.chat({
                session_id: state.sessionId,
                message: text,
                history: toApiHistory(),
            });

            const serverSession = String(response.session_id || "").trim();
            if (serverSession) {
                state.sessionId = api.setChatSessionId(serverSession) || serverSession;
            }

            appendMessage({
                role: "assistant",
                content: response.answer || "Không có phản hồi.",
                time: nowLabel(),
                grounding: response.grounding || {},
                citations: response.citations || [],
                fallback: !!response.fallback,
            });
        } catch (error) {
            appendMessage({
                role: "assistant",
                content: error.message || "Không thể kết nối trợ lý lúc này.",
                time: nowLabel(),
                grounding: {},
                citations: [],
                fallback: true,
            });
        } finally {
            setSending(false);
            if (chatInput) {
                chatInput.focus();
            }
        }
    }

    async function clearConversation() {
        const confirmed = window.confirm("Xóa toàn bộ hội thoại hiện tại?");
        if (!confirmed || state.sending) {
            return;
        }

        setSending(true);
        try {
            await api.clearChatHistory(state.sessionId);
            state.sessionId = api.resetChatSessionId();
            state.messages = [];
            saveHistoryCache();
            renderMessages();
        } catch (error) {
            window.alert(error.message || "Không thể xóa hội thoại lúc này.");
        } finally {
            setSending(false);
        }
    }

    function loadSeedQuestion() {
        try {
            const raw = sessionStorage.getItem(CHAT_SEED_KEY);
            if (!raw) {
                return "";
            }
            sessionStorage.removeItem(CHAT_SEED_KEY);
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed.prompt !== "string") {
                return "";
            }
            return parsed.prompt.trim();
        } catch (error) {
            return "";
        }
    }

    if (chatForm) {
        chatForm.addEventListener("submit", function (event) {
            event.preventDefault();
            sendMessage(chatInput.value);
        });
    }

    if (chatInput) {
        chatInput.addEventListener("keydown", function (event) {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendMessage(chatInput.value);
            }
        });
    }

    if (quickQuestionRow) {
        quickQuestionRow.addEventListener("click", function (event) {
            const button = event.target.closest(".quick-question");
            if (!button) {
                return;
            }
            sendMessage(button.dataset.question || "");
        });
    }

    if (btnClearChat) {
        btnClearChat.addEventListener("click", clearConversation);
    }

    state.sessionId = api.getChatSessionId ? api.getChatSessionId() : "";
    await hydrateHistory();
    renderMessages();

    const seededPrompt = loadSeedQuestion();
    if (seededPrompt) {
        sendMessage(seededPrompt);
    }
});
