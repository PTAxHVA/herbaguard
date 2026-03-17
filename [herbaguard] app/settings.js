document.addEventListener("DOMContentLoaded", function () {
    const api = window.HerbaGuardAPI;
    if (!api) {
        return;
    }

    const toggleVoice = document.getElementById("toggleVoice");
    const toggleLargeText = document.getElementById("toggleLargeText");
    const toggleNotifications = document.getElementById("toggleNotifications");
    const selectTheme = document.getElementById("selectTheme");
    const btnSaveSettings = document.getElementById("btnSaveSettings");
    const btnTestVoice = document.getElementById("btnTestVoice");
    const settingsMessage = document.getElementById("settingsMessage");

    const guideDialog = document.getElementById("guideDialog");
    const btnGuideVideo = document.getElementById("btnGuideVideo");
    const btnCloseGuide = document.getElementById("btnCloseGuide");

    let currentSettings = {
        voice_enabled: false,
        large_text: false,
        theme: "light",
        browser_notifications: false,
    };
    let submitting = false;

    function showMessage(type, text) {
        if (!settingsMessage) {
            return;
        }

        if (!text) {
            settingsMessage.textContent = "";
            settingsMessage.className = "status-message hidden";
            return;
        }

        settingsMessage.textContent = text;
        settingsMessage.className = `status-message ${type}`;
    }

    function setSubmitting(isSubmitting) {
        submitting = isSubmitting;
        const controls = [toggleVoice, toggleLargeText, toggleNotifications, selectTheme, btnSaveSettings, btnTestVoice];
        controls.forEach((control) => {
            if (control) {
                control.disabled = isSubmitting;
            }
        });
    }

    function syncForm(settings) {
        currentSettings = {
            voice_enabled: !!settings.voice_enabled,
            large_text: !!settings.large_text,
            theme: settings.theme === "dark" ? "dark" : "light",
            browser_notifications: !!settings.browser_notifications,
        };

        if (toggleVoice) {
            toggleVoice.checked = currentSettings.voice_enabled;
        }
        if (toggleLargeText) {
            toggleLargeText.checked = currentSettings.large_text;
        }
        if (toggleNotifications) {
            toggleNotifications.checked = currentSettings.browser_notifications;
        }
        if (selectTheme) {
            selectTheme.value = currentSettings.theme;
        }
    }

    async function requestNotificationPermissionIfNeeded(enabled) {
        if (!enabled) {
            return true;
        }

        if (!("Notification" in window)) {
            showMessage("warning", "Trình duyệt này không hỗ trợ Notification API.");
            return false;
        }

        if (Notification.permission === "granted") {
            return true;
        }

        if (Notification.permission === "denied") {
            showMessage("warning", "Thông báo đã bị chặn trong trình duyệt. Hãy bật lại trong phần quyền truy cập.");
            return false;
        }

        const permission = await Notification.requestPermission();
        if (permission !== "granted") {
            showMessage("warning", "Bạn chưa cấp quyền thông báo. Cài đặt sẽ giữ trạng thái tắt.");
            return false;
        }
        return true;
    }

    async function saveSettings() {
        if (submitting) {
            return;
        }

        const requestedSettings = {
            voice_enabled: !!toggleVoice.checked,
            large_text: !!toggleLargeText.checked,
            theme: selectTheme.value === "dark" ? "dark" : "light",
            browser_notifications: !!toggleNotifications.checked,
        };

        const canEnableNotification = await requestNotificationPermissionIfNeeded(requestedSettings.browser_notifications);
        if (!canEnableNotification) {
            requestedSettings.browser_notifications = false;
            if (toggleNotifications) {
                toggleNotifications.checked = false;
            }
        }

        setSubmitting(true);
        showMessage("", "");

        try {
            const updated = await api.updateSettings(requestedSettings);
            syncForm(updated);

            if (window.HerbaGuardApp && window.HerbaGuardApp.applySettings) {
                window.HerbaGuardApp.applySettings(updated);
            }

            showMessage("success", "Đã lưu cài đặt thành công.");
        } catch (error) {
            syncForm(currentSettings);
            showMessage("error", error.message || "Không thể lưu cài đặt lúc này.");
        } finally {
            setSubmitting(false);
        }
    }

    function testVoice() {
        if (!window.speechSynthesis || typeof window.SpeechSynthesisUtterance !== "function") {
            showMessage("warning", "Trình duyệt hiện tại không hỗ trợ đọc giọng nói.");
            return;
        }

        if (!toggleVoice.checked) {
            showMessage("warning", "Hãy bật tùy chọn giọng nói trước khi nghe thử.");
            return;
        }

        const utterance = new SpeechSynthesisUtterance(
            "HerbaGuard đang đọc thử giọng tiếng Việt. Bạn có thể dùng tính năng này khi xem kết quả tương tác."
        );
        utterance.lang = "vi-VN";
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
        showMessage("success", "Đang đọc thử giọng nói.");
    }

    async function init() {
        setSubmitting(true);
        try {
            const settings = await api.getSettings();
            syncForm(settings);
            if (window.HerbaGuardApp && window.HerbaGuardApp.applySettings) {
                window.HerbaGuardApp.applySettings(settings);
            }
        } catch (error) {
            showMessage("error", error.message || "Không thể tải cài đặt.");
        } finally {
            setSubmitting(false);
        }
    }

    if (btnSaveSettings) {
        btnSaveSettings.addEventListener("click", saveSettings);
    }

    if (btnTestVoice) {
        btnTestVoice.addEventListener("click", testVoice);
    }

    if (btnGuideVideo) {
        btnGuideVideo.addEventListener("click", function () {
            if (guideDialog && guideDialog.showModal) {
                guideDialog.showModal();
            }
        });
    }

    if (btnCloseGuide) {
        btnCloseGuide.addEventListener("click", function () {
            if (guideDialog && guideDialog.close) {
                guideDialog.close();
            }
        });
    }

    [toggleVoice, toggleLargeText, toggleNotifications, selectTheme].forEach((element) => {
        if (!element) {
            return;
        }
        element.addEventListener("change", function () {
            showMessage("", "");
        });
    });

    init();
});
