document.addEventListener("DOMContentLoaded", function () {
    const api = window.HerbaGuardAPI;
    if (!api) {
        return;
    }

    function showMessage(el, type, message) {
        if (!el) {
            return;
        }
        el.classList.remove("hidden", "error", "success");
        el.classList.add(type);
        el.textContent = message;
    }

    const loginForm = document.getElementById("loginForm");
    if (loginForm) {
        const msgEl = document.getElementById("loginMessage");
        const submitEl = document.getElementById("loginSubmit");

        loginForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            const form = new FormData(loginForm);
            const email = String(form.get("email") || "").trim();
            const password = String(form.get("password") || "");

            submitEl.disabled = true;
            if (msgEl) {
                msgEl.classList.add("hidden");
            }

            try {
                const response = await api.login({ email: email, password: password });
                api.setSession(response.token, response.user);
                showMessage(msgEl, "success", "Đăng nhập thành công. Đang chuyển trang...");
                setTimeout(() => {
                    window.location.href = "index.html";
                }, 500);
            } catch (error) {
                showMessage(msgEl, "error", error.message || "Đăng nhập thất bại.");
            } finally {
                submitEl.disabled = false;
            }
        });
    }

    const registerForm = document.getElementById("registerForm");
    if (registerForm) {
        const msgEl = document.getElementById("registerMessage");
        const submitEl = document.getElementById("registerSubmit");

        registerForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            const form = new FormData(registerForm);

            const fullName = String(form.get("fullName") || "").trim();
            const email = String(form.get("email") || "").trim();
            const password = String(form.get("password") || "");
            const confirmPassword = String(form.get("confirmPassword") || "");

            if (password !== confirmPassword) {
                showMessage(msgEl, "error", "Mật khẩu nhập lại không khớp.");
                return;
            }

            submitEl.disabled = true;
            if (msgEl) {
                msgEl.classList.add("hidden");
            }

            try {
                const response = await api.register({
                    full_name: fullName,
                    email: email,
                    password: password,
                });
                api.setSession(response.token, response.user);
                showMessage(msgEl, "success", "Đăng ký thành công. Đang chuyển trang...");
                setTimeout(() => {
                    window.location.href = "index.html";
                }, 500);
            } catch (error) {
                showMessage(msgEl, "error", error.message || "Đăng ký thất bại.");
            } finally {
                submitEl.disabled = false;
            }
        });
    }
});
