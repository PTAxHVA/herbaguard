// Đợi cho đến khi HTML tải xong toàn bộ mới chạy mã JS
document.addEventListener("DOMContentLoaded", function () {
    
    // --- 1. LOGIC LỜI CHÀO THEO THỜI GIAN THỰC ---
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

    // --- 2. LOGIC TÌM KIẾM Ở HERO BANNER ---
    const btnHeroCheck = document.getElementById("btn-hero-check");
    const heroSearchInput = document.getElementById("hero-search-input");

    if (btnHeroCheck && heroSearchInput) {
        btnHeroCheck.addEventListener("click", function () {
            const medicineName = heroSearchInput.value.trim();
            
            // Nếu người dùng có nhập tên thuốc, lưu nó vào Local Storage
            if (medicineName !== "") {
                localStorage.setItem("searchMedicine", medicineName);
            }
            
            // Chuyển hướng sang trang Quét Thuốc
            window.location.href = "check.html";
        });

        // Cho phép ấn Enter để tìm kiếm luôn
        heroSearchInput.addEventListener("keypress", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                btnHeroCheck.click();
            }
        });
    }

    // --- 3. LOGIC CHUYỂN TRANG CHO CÁC THẺ (CARDS) ---
    const cardScan = document.getElementById("card-scan");
    if (cardScan) {
        cardScan.addEventListener("click", () => window.location.href = "check.html");
    }

    const cardMeds = document.getElementById("card-meds");
    if (cardMeds) {
        cardMeds.addEventListener("click", () => window.location.href = "medicines.html");
    }

    const cardVoice = document.getElementById("card-voice");
    if (cardVoice) {
        cardVoice.addEventListener("click", () => window.location.href = "settings.html");
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

    // --- 4. LOGIC THÔNG BÁO ---
    const btnNotification = document.getElementById("btn-notification");
    if (btnNotification) {
        btnNotification.addEventListener("click", function () {
            alert("Bạn đang có 1 thông báo nhắc nhở uống thuốc sắp tới!");
        });
    }
    
    // --- 5. LOGIC KHẨN CẤP (Gọi điện) ---
    const cardEmergency = document.getElementById("card-emergency");
    if (cardEmergency) {
        cardEmergency.addEventListener("click", function () {
            // Giả lập chức năng gọi điện
            const confirmCall = confirm("Phát tín hiệu KHẨN CẤP tới người thân?");
            if (confirmCall) {
                window.location.href = "tel:115"; // Gọi khẩn cấp thực tế trên điện thoại
            }
        });
    }

});