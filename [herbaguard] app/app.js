document.addEventListener("DOMContentLoaded", async function () {
    const PUBLIC_PAGES = new Set(["login.html", "register.html"]);
    const api = window.HerbaGuardAPI || null;

    const pathname = window.location.pathname || "/";
    const rawPage = pathname.split("/").pop() || "index.html";
    const currentPage = rawPage === "" ? "index.html" : rawPage;
    const isPublicPage = PUBLIC_PAGES.has(currentPage);

    const token = api && api.getToken ? api.getToken() : (localStorage.getItem("herbaguard:authToken") || "");
    let currentUser = api && api.getUser ? api.getUser() : null;
    let currentSettings = api && api.getCachedSettings ? api.getCachedSettings() : null;

    function applySettings(settings) {
        if (!settings) {
            return;
        }

        document.body.classList.toggle("large-text", !!settings.large_text);
        document.body.classList.toggle("theme-dark", settings.theme === "dark");

        if (api && api.setCachedSettings) {
            api.setCachedSettings(settings);
        }
        currentSettings = settings;
    }

    function speakText(text) {
        if (!text || !window.speechSynthesis || !currentSettings || !currentSettings.voice_enabled) {
            return;
        }

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "vi-VN";
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
    }

    async function redirectToLogin() {
        window.location.href = "login.html";
    }

    if (isPublicPage) {
        if (token && api && api.me) {
            try {
                const me = await api.me();
                api.setSession(token, me);
                window.location.href = "index.html";
                return;
            } catch (error) {
                api.clearSession();
            }
        }
    } else {
        if (!token) {
            await redirectToLogin();
            return;
        }

        if (api && api.me) {
            try {
                const me = await api.me();
                currentUser = me;
                api.setSession(token, me);
            } catch (error) {
                if (api && api.clearSession) {
                    api.clearSession();
                }
                await redirectToLogin();
                return;
            }
        }

        if (api && api.getSettings) {
            try {
                const settings = await api.getSettings();
                applySettings(settings);
            } catch (error) {
                // Ignore settings failure, app still usable.
            }
        }
    }

    if (!currentSettings && api && api.getCachedSettings) {
        currentSettings = api.getCachedSettings();
        applySettings(currentSettings);
    }

    if (currentUser) {
        const userNameElements = document.querySelectorAll(".user-info p:last-child");
        userNameElements.forEach((el) => {
            el.textContent = currentUser.full_name;
        });

        const profileName = document.getElementById("profile-name");
        if (profileName) {
            profileName.textContent = currentUser.full_name;
        }

        const profileEmail = document.getElementById("profile-email");
        if (profileEmail) {
            profileEmail.textContent = currentUser.email;
        }

        const avatarUrl = `https://ui-avatars.com/api/?name=${encodeURIComponent(currentUser.full_name)}&background=10B981&color=fff`;
        const navAvatar = document.getElementById("nav-avatar");
        if (navAvatar) {
            navAvatar.src = avatarUrl;
        }

        const profileAvatar = document.getElementById("profile-avatar");
        if (profileAvatar) {
            profileAvatar.src = avatarUrl;
        }
    }

    const greetingElement = document.getElementById("greeting-text");
    if (greetingElement) {
        const currentHour = new Date().getHours();
        let greeting = "Xin chào,";

        if (currentHour >= 5 && currentHour < 12) {
            greeting = "Chào buổi sáng,";
        } else if (currentHour >= 12 && currentHour < 18) {
            greeting = "Chào buổi chiều,";
        } else if (currentHour >= 18 || currentHour < 5) {
            greeting = "Chào buổi tối,";
        }

        greetingElement.textContent = greeting;
    }

    const navLogo = document.getElementById("nav-logo");
    if (navLogo) {
        navLogo.addEventListener("click", () => window.location.href = "index.html");
    }

    const navAvatar = document.getElementById("nav-avatar");
    if (navAvatar) {
        navAvatar.addEventListener("click", () => window.location.href = "settings.html");
    }

    const btnViewAllMeds = document.getElementById("btn-view-all-meds");
    if (btnViewAllMeds) {
        btnViewAllMeds.addEventListener("click", () => window.location.href = "medicines.html");
    }

    const btnNotification = document.getElementById("btn-notification");
    if (btnNotification) {
        btnNotification.addEventListener("click", async function () {
            if (!api || !api.getDashboard || isPublicPage) {
                return;
            }
            try {
                const data = await api.getDashboard();
                if (!data.alerts || data.alerts.length === 0) {
                    alert("Hiện chưa có cảnh báo mới.");
                    return;
                }

                const lines = data.alerts.slice(0, 4).map((item) => `• ${item.title}: ${item.message}`);
                alert(["Thông báo mới:", ...lines].join("\n"));
            } catch (error) {
                alert("Không thể tải thông báo lúc này.");
            }
        });
    }

    document.querySelectorAll("[data-open-chat='true']").forEach((el) => {
        el.addEventListener("click", function () {
            window.location.href = "chat.html";
        });
    });

    const btnLogout = document.getElementById("btn-logout");
    if (btnLogout) {
        btnLogout.addEventListener("click", async function () {
            const confirmed = confirm("Bạn có chắc muốn đăng xuất?");
            if (!confirmed) {
                return;
            }

            if (api && api.logout) {
                await api.logout();
            } else {
                localStorage.removeItem("herbaguard:authToken");
                localStorage.removeItem("herbaguard:authUser");
            }
            window.location.href = "login.html";
        });
    }

    window.HerbaGuardApp = {
        user: currentUser,
        settings: currentSettings,
        applySettings,
        speakText,
    };
});
