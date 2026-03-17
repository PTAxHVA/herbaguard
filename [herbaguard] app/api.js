(function initHerbaGuardAPI(global) {
    const AUTH_TOKEN_KEY = "herbaguard:authToken";
    const AUTH_USER_KEY = "herbaguard:authUser";
    const SETTINGS_KEY = "herbaguard:settings";
    const CHAT_SESSION_PREFIX = "herbaguard:chatSession:";

    function getToken() {
        return localStorage.getItem(AUTH_TOKEN_KEY) || "";
    }

    function getUser() {
        const raw = localStorage.getItem(AUTH_USER_KEY);
        if (!raw) {
            return null;
        }
        try {
            return JSON.parse(raw);
        } catch (error) {
            return null;
        }
    }

    function setSession(token, user) {
        localStorage.setItem(AUTH_TOKEN_KEY, token || "");
        localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user || null));
    }

    function clearSession() {
        localStorage.removeItem(AUTH_TOKEN_KEY);
        localStorage.removeItem(AUTH_USER_KEY);
        localStorage.removeItem(SETTINGS_KEY);
        const keysToRemove = [];
        for (let index = 0; index < localStorage.length; index += 1) {
            const key = localStorage.key(index);
            if (key && key.startsWith(CHAT_SESSION_PREFIX)) {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach((key) => localStorage.removeItem(key));
    }

    function generateSessionId() {
        if (global.crypto && typeof global.crypto.randomUUID === "function") {
            return global.crypto.randomUUID();
        }
        return `sess-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    }

    function getChatSessionStorageKey() {
        const user = getUser();
        const scope = user && user.id ? String(user.id) : "guest";
        return `${CHAT_SESSION_PREFIX}${scope}`;
    }

    function getChatSessionId() {
        const key = getChatSessionStorageKey();
        let sessionId = localStorage.getItem(key);
        if (!sessionId) {
            sessionId = generateSessionId();
            localStorage.setItem(key, sessionId);
        }
        return sessionId;
    }

    function setChatSessionId(sessionId) {
        const cleaned = String(sessionId || "").trim();
        if (!cleaned) {
            return "";
        }
        localStorage.setItem(getChatSessionStorageKey(), cleaned);
        return cleaned;
    }

    function resetChatSessionId() {
        const newSessionId = generateSessionId();
        setChatSessionId(newSessionId);
        return newSessionId;
    }

    function getCachedSettings() {
        const raw = localStorage.getItem(SETTINGS_KEY);
        if (!raw) {
            return null;
        }
        try {
            return JSON.parse(raw);
        } catch (error) {
            return null;
        }
    }

    function setCachedSettings(settings) {
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings || {}));
    }

    async function request(path, options) {
        const authRequired = options && options.auth === true;
        const token = getToken();

        const headers = {
            "Content-Type": "application/json",
            ...(options && options.headers ? options.headers : {}),
        };
        if (authRequired && token) {
            headers.Authorization = `Bearer ${token}`;
        }

        const requestOptions = {
            headers: headers,
            ...options,
        };
        if ("auth" in requestOptions) {
            delete requestOptions.auth;
        }

        const response = await fetch(path, requestOptions);
        const contentType = response.headers.get("content-type") || "";

        let payload = null;
        if (contentType.includes("application/json")) {
            payload = await response.json();
        } else {
            payload = { detail: await response.text() };
        }

        if (!response.ok) {
            const message = payload && payload.detail ? payload.detail : `Lỗi ${response.status}`;
            throw new Error(message);
        }

        return payload;
    }

    async function register(payload) {
        return request("/api/auth/register", {
            method: "POST",
            body: JSON.stringify(payload),
        });
    }

    async function login(payload) {
        return request("/api/auth/login", {
            method: "POST",
            body: JSON.stringify(payload),
        });
    }

    async function me() {
        return request("/api/auth/me", { method: "GET", auth: true });
    }

    async function logout() {
        try {
            await request("/api/auth/logout", { method: "POST", auth: true });
        } finally {
            clearSession();
        }
    }

    async function getSettings() {
        const settings = await request("/api/settings", { method: "GET", auth: true });
        setCachedSettings(settings);
        return settings;
    }

    async function updateSettings(payload) {
        const settings = await request("/api/settings", {
            method: "PUT",
            auth: true,
            body: JSON.stringify(payload),
        });
        setCachedSettings(settings);
        return settings;
    }

    async function getDashboard() {
        return request("/api/dashboard", { method: "GET", auth: true });
    }

    async function search(query) {
        const data = await request(`/api/search?q=${encodeURIComponent(query)}`);
        return data.results || [];
    }

    async function checkInteraction(items) {
        return request("/api/check-interaction", {
            method: "POST",
            auth: true,
            body: JSON.stringify({ items: items }),
        });
    }

    async function chat(payload) {
        return request("/api/chat", {
            method: "POST",
            auth: true,
            body: JSON.stringify(payload),
        });
    }

    async function getChatHistory(sessionId, limit) {
        const safeSession = String(sessionId || "").trim();
        if (!safeSession) {
            throw new Error("Thiếu session_id cho lịch sử chat.");
        }
        const params = new URLSearchParams({ session_id: safeSession });
        if (typeof limit === "number" && Number.isFinite(limit)) {
            params.set("limit", String(limit));
        }
        return request(`/api/chat/history?${params.toString()}`, {
            method: "GET",
            auth: true,
        });
    }

    async function clearChatHistory(sessionId) {
        const safeSession = String(sessionId || "").trim();
        if (!safeSession) {
            throw new Error("Thiếu session_id để xóa lịch sử chat.");
        }
        const params = new URLSearchParams({ session_id: safeSession });
        return request(`/api/chat/history?${params.toString()}`, {
            method: "DELETE",
            auth: true,
        });
    }

    async function listMedicines() {
        return request("/api/medicines", { method: "GET", auth: true });
    }

    async function createMedicine(payload) {
        return request("/api/medicines", {
            method: "POST",
            auth: true,
            body: JSON.stringify(payload),
        });
    }

    async function updateMedicine(id, payload) {
        return request(`/api/medicines/${id}`, {
            method: "PUT",
            auth: true,
            body: JSON.stringify(payload),
        });
    }

    async function deleteMedicine(id) {
        return request(`/api/medicines/${id}`, {
            method: "DELETE",
            auth: true,
        });
    }

    async function listReminders() {
        return request("/api/reminders", { method: "GET", auth: true });
    }

    async function createReminder(payload) {
        return request("/api/reminders", {
            method: "POST",
            auth: true,
            body: JSON.stringify(payload),
        });
    }

    async function updateReminder(id, payload) {
        return request(`/api/reminders/${id}`, {
            method: "PUT",
            auth: true,
            body: JSON.stringify(payload),
        });
    }

    async function deleteReminder(id) {
        return request(`/api/reminders/${id}`, {
            method: "DELETE",
            auth: true,
        });
    }

    async function getCheckHistory(limit) {
        const q = typeof limit === "number" ? `?limit=${encodeURIComponent(limit)}` : "";
        return request(`/api/check-history${q}`, { method: "GET", auth: true });
    }

    global.HerbaGuardAPI = {
        register,
        login,
        me,
        logout,
        getToken,
        getUser,
        setSession,
        clearSession,
        getCachedSettings,
        setCachedSettings,
        getChatSessionId,
        setChatSessionId,
        resetChatSessionId,
        getSettings,
        updateSettings,
        getDashboard,
        search,
        checkInteraction,
        chat,
        getChatHistory,
        clearChatHistory,
        listMedicines,
        createMedicine,
        updateMedicine,
        deleteMedicine,
        listReminders,
        createReminder,
        updateReminder,
        deleteReminder,
        getCheckHistory,
    };
})(window);
