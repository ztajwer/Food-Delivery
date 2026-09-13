/* ==========================================================================
   AURA DIGITAL CULINARY EXHIBITION - MAIN APPLICATION ENGINE
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Lucide Icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // 2. Synchronize Lenis Smooth Scroll with GSAP & ScrollTrigger
    let lenis;
    if (typeof Lenis !== 'undefined' && typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
        lenis = new Lenis({
            duration: 0.8,
            easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
            orientation: 'vertical',
            gestureOrientation: 'vertical',
            smoothWheel: true,
            wheelMultiplier: 1.2,
            touchMultiplier: 1.5
        });

        lenis.on('scroll', ScrollTrigger.update);
        gsap.ticker.add((time) => lenis.raf(time * 1000));
        gsap.ticker.lagSmoothing(0);
    }

    // --- 3. DARK / LIGHT THEME SWITCHER LOGIC ---
    const themeToggleBtn = document.getElementById('themeToggleBtn');
    let currentTheme = localStorage.getItem('aura-theme') || 'dark';

    function applyTheme(theme) {
        currentTheme = theme;
        localStorage.setItem('aura-theme', theme);
        const isLight = (theme === 'light');

        if (isLight) {
            document.body.classList.remove('dark-theme');
            document.body.classList.add('light-theme');
        } else {
            document.body.classList.remove('light-theme');
            document.body.classList.add('dark-theme');
        }

        if (window.update3DTheme) {
            window.update3DTheme(isLight);
        }
    }

    applyTheme(currentTheme);

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            const nextTheme = (currentTheme === 'dark') ? 'light' : 'dark';
            applyTheme(nextTheme);
            showToast(`Switched to ${nextTheme.toUpperCase()} theme mode.`);
        });
    }

    // --- 4. FOOD MENU DATABASE ---
    const menuData = [
        {
            id: 1,
            indexStr: "01",
            name: "AURA Prime Wagyu Truffle",
            category: "burgers",
            price: 28.50,
            image: "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=800&q=80",
            desc: "A5 Miyazaki Wagyu patty, 18-month aged English cheddar, black winter truffle aioli on a gilded brioche bun.",
            badge: "Signature Creation",
            prepTime: "18 mins",
            calories: "820 kcal",
            tags: ["A5 Wagyu", "Piedmont Truffle", "Gold Brioche"]
        },
        {
            id: 2,
            indexStr: "02",
            name: "Smokey Chipotle Crunch",
            category: "burgers",
            price: 22.00,
            image: "https://images.unsplash.com/photo-1586190848861-99aa4a171e90?auto=format&fit=crop&w=800&q=80",
            desc: "Flame-seared Angus beef, double crisp smoked bacon, spicy chipotle spread, crisp hydroponic heirloom greens.",
            badge: "Spicy Ember",
            prepTime: "15 mins",
            calories: "740 kcal",
            tags: ["Spicy", "Crisp Bacon", "Chipotle"]
        },
        {
            id: 3,
            indexStr: "03",
            name: "Artisan Black Truffle Pizza",
            category: "pizza",
            price: 32.00,
            image: "https://images.unsplash.com/photo-1513104890138-7c749659a591?auto=format&fit=crop&w=800&q=80",
            desc: "48-hour fermented sourdough crust, fior di latte mozzarella, shaved fresh black winter truffle.",
            badge: "Wood-Fired",
            prepTime: "20 mins",
            calories: "910 kcal",
            tags: ["Sourdough", "Vegetarian", "Winter Truffle"]
        },
        {
            id: 4,
            indexStr: "04",
            name: "Prosciutto & Wild Fig Flatbread",
            category: "pizza",
            price: 26.50,
            image: "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?auto=format&fit=crop&w=800&q=80",
            desc: "Aged Parma prosciutto, caramelised Black Mission figs, wild arugula, honey balsamico glaze.",
            badge: "Best Seller",
            prepTime: "16 mins",
            calories: "680 kcal",
            tags: ["Sweet & Savory", "Parma Prosciutto"]
        },
        {
            id: 5,
            indexStr: "05",
            name: "Golden Harissa Salmon Bowl",
            category: "bowls",
            price: 27.00,
            image: "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=800&q=80",
            desc: "Wild Atlantic salmon glazed with golden harissa, tri-color organic quinoa, roasted hass avocado, edamame.",
            badge: "High Protein",
            prepTime: "14 mins",
            calories: "590 kcal",
            tags: ["Gluten-Free", "Wild Salmon"]
        },
        {
            id: 6,
            indexStr: "06",
            name: "Zen Matcha Avocado Poke",
            category: "bowls",
            price: 21.50,
            image: "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&w=800&q=80",
            desc: "Organic yellowfin tuna poke, hass avocado, pickled daikon, spicy sesame emulsion on purple wild rice.",
            badge: "Organic",
            prepTime: "12 mins",
            calories: "520 kcal",
            tags: ["Omega-3", "Fresh Poke"]
        },
        {
            id: 7,
            indexStr: "07",
            name: "Smoked Ember Old Fashioned",
            category: "drinks",
            price: 18.00,
            image: "https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?auto=format&fit=crop&w=800&q=80",
            desc: "Single-barrel bourbon, hickory wood smoke infusion, hand-carved crystal ice sphere.",
            badge: "Craft Elixir",
            prepTime: "5 mins",
            calories: "160 kcal",
            tags: ["Craft Cocktail", "Wood Smoke"]
        },
        {
            id: 8,
            indexStr: "08",
            name: "Sparkling Yuzu Botanical",
            category: "drinks",
            price: 12.00,
            image: "https://images.unsplash.com/photo-1551024709-8f23befc6f87?auto=format&fit=crop&w=800&q=80",
            desc: "Pressed Japanese yuzu fruit, elderflower syrup, wild garden mint, sparkling artisanal tonic.",
            badge: "Zero Proof",
            prepTime: "4 mins",
            calories: "90 kcal",
            tags: ["Refreshing", "Zero Proof"]
        }
    ];

    // --- 5. RENDER MENU ITEMS (GRID & LIST LAYOUT MODES) ---
    const menuGrid = document.getElementById('menuGrid');
    const categoryFilters = document.getElementById('categoryFilters');
    const viewToggleGrid = document.getElementById('viewToggleGrid');
    const viewToggleList = document.getElementById('viewToggleList');

    let currentViewMode = 'grid';
    let currentCategory = 'all';

    function renderMenu() {
        if (!menuGrid) return;
        menuGrid.innerHTML = '';

        const items = (currentCategory === 'all')
            ? menuData
            : menuData.filter(item => item.category === currentCategory);

        if (currentViewMode === 'grid') {
            menuGrid.className = 'menu-display-container grid-mode';
            items.forEach(item => {
                const card = document.createElement('div');
                card.className = 'food-card-grid';
                card.setAttribute('data-id', item.id);

                card.innerHTML = `
                    <div class="food-img-wrap">
                        <img src="${item.image}" alt="${item.name}" class="food-img" loading="lazy">
                        <span class="food-badge"><i data-lucide="sparkles"></i> ${item.badge}</span>
                    </div>
                    <div class="food-card-body">
                        <div class="food-title-row">
                            <h3>${item.name}</h3>
                            <span class="food-price">$${item.price.toFixed(2)}</span>
                        </div>
                        <p>${item.desc}</p>
                        <div class="food-card-footer">
                            <div class="food-meta">
                                <span class="food-meta-item"><i data-lucide="clock"></i> ${item.prepTime}</span>
                                <span class="food-meta-item"><i data-lucide="flame"></i> ${item.calories}</span>
                            </div>
                            <button class="btn btn-primary btn-sm add-cart-btn" data-id="${item.id}">
                                <span>Order</span>
                                <i data-lucide="plus"></i>
                            </button>
                        </div>
                    </div>
                `;

                card.addEventListener('click', (e) => {
                    if (e.target.closest('.add-cart-btn')) return;
                    openFoodModal(item);
                });

                menuGrid.appendChild(card);
            });
        } else {
            menuGrid.className = 'menu-display-container list-mode';
            items.forEach(item => {
                const row = document.createElement('div');
                row.className = 'editorial-menu-row';
                row.setAttribute('data-id', item.id);

                row.innerHTML = `
                    <span class="menu-row-num">${item.indexStr}</span>
                    <img src="${item.image}" alt="${item.name}" class="food-preview-hover" loading="lazy">
                    <div class="menu-row-info">
                        <h3>${item.name}</h3>
                        <p>${item.desc}</p>
                    </div>
                    <span class="menu-row-price">$${item.price.toFixed(2)}</span>
                    <div class="menu-row-actions">
                        <button class="btn btn-outline btn-sm quick-view-btn" data-id="${item.id}">
                            <span>Details</span>
                        </button>
                        <button class="btn btn-primary btn-sm add-cart-btn" data-id="${item.id}">
                            <span>Order</span>
                            <i data-lucide="plus"></i>
                        </button>
                    </div>
                `;

                row.addEventListener('click', (e) => {
                    if (e.target.closest('.add-cart-btn')) return;
                    openFoodModal(item);
                });

                menuGrid.appendChild(row);
            });
        }

        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    if (categoryFilters) {
        categoryFilters.addEventListener('click', (e) => {
            const filterBtn = e.target.closest('.filter-btn');
            if (!filterBtn) return;

            categoryFilters.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            filterBtn.classList.add('active');

            currentCategory = filterBtn.getAttribute('data-category');
            renderMenu();
        });
    }

    if (viewToggleGrid && viewToggleList) {
        viewToggleGrid.addEventListener('click', () => {
            currentViewMode = 'grid';
            viewToggleGrid.classList.add('active');
            viewToggleList.classList.remove('active');
            renderMenu();
        });

        viewToggleList.addEventListener('click', () => {
            currentViewMode = 'list';
            viewToggleList.classList.add('active');
            viewToggleGrid.classList.remove('active');
            renderMenu();
        });
    }

    renderMenu();

    // --- 6. EDITORIAL CHAPTER PROGRESS & COLOR THEME TRACKING ---
    const chapterNum = document.getElementById('chapterNum');
    const chapterTitle = document.getElementById('chapterTitle');
    const chapterSections = document.querySelectorAll('.chapter-section');

    if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
        chapterSections.forEach(sec => {
            ScrollTrigger.create({
                trigger: sec,
                start: "top 50%",
                end: "bottom 50%",
                onEnter: () => updateChapter(sec),
                onEnterBack: () => updateChapter(sec)
            });
        });
    }

    function updateChapter(section) {
        const num = section.getAttribute('data-chapter');
        const title = section.getAttribute('data-title');
        const theme = section.getAttribute('data-theme');

        if (chapterNum && num) chapterNum.textContent = `${num} / 07`;
        if (chapterTitle && title) chapterTitle.textContent = title;

        if (theme) {
            document.body.classList.remove('theme-charcoal', 'theme-cream', 'theme-fire', 'theme-emerald', 'theme-slate', 'theme-onyx');
            document.body.classList.add(theme);
        }
    }

    // --- 7. SHOPPING CART SYSTEM & FLYING ANIMATION ---
    let cart = [];
    try {
        const savedCart = JSON.parse(localStorage.getItem('ispice-cart') || '[]');
        if (Array.isArray(savedCart)) cart = savedCart.filter(item => item && Number.isFinite(item.id) && item.qty > 0);
    } catch (_) {
        localStorage.removeItem('ispice-cart');
    }
    const cartOverlay = document.getElementById('cartOverlay');
    const cartDrawer = document.getElementById('cartDrawer');
    const cartToggleBtn = document.getElementById('cartToggleBtn');
    const closeCartBtn = document.getElementById('closeCartBtn');
    const cartItemsList = document.getElementById('cartItemsList');
    const cartEmpty = document.getElementById('cartEmpty');
    const cartFooter = document.getElementById('cartFooter');
    const cartCount = document.getElementById('cartCount');
    const cartSubtotal = document.getElementById('cartSubtotal');
    const cartTotal = document.getElementById('cartTotal');
    const checkoutBtn = document.getElementById('checkoutBtn');

    function toggleCart(open) {
        if (!cartOverlay || !cartDrawer) return;
        if (open) {
            cartOverlay.classList.add('active');
            cartDrawer.classList.add('active');
        } else {
            cartOverlay.classList.remove('active');
            cartDrawer.classList.remove('active');
        }
    }

    if (cartToggleBtn) cartToggleBtn.addEventListener('click', () => toggleCart(true));
    if (closeCartBtn) closeCartBtn.addEventListener('click', () => toggleCart(false));
    if (cartOverlay) cartOverlay.addEventListener('click', () => toggleCart(false));

    function animateFlyToCart(sourceEl) {
        if (!sourceEl || !cartToggleBtn) return;
        const rect = sourceEl.getBoundingClientRect();
        const flyEl = document.createElement('div');
        flyEl.style.position = 'fixed';
        flyEl.style.top = `${rect.top}px`;
        flyEl.style.left = `${rect.left}px`;
        flyEl.style.width = '24px';
        flyEl.style.height = '24px';
        flyEl.style.borderRadius = '50%';
        flyEl.style.background = 'var(--primary)';
        flyEl.style.zIndex = '9999';
        flyEl.style.pointerEvents = 'none';
        flyEl.style.boxShadow = '0 0 15px var(--primary)';
        document.body.appendChild(flyEl);

        const targetRect = cartToggleBtn.getBoundingClientRect();
        const animate = (typeof gsap !== 'undefined') ? gsap.to : null;
        if (!animate) {
            flyEl.remove();
            return;
        }
        animate(flyEl, {
            x: targetRect.left - rect.left,
            y: targetRect.top - rect.top,
            scale: 0.2,
            duration: 0.75,
            ease: "power2.inOut",
            onComplete: () => {
                flyEl.remove();
                gsap.fromTo(cartToggleBtn, { scale: 1.3 }, { scale: 1, duration: 0.3 });
            }
        });
    }

    function addToCart(foodId, sourceBtn) {
        const foodItem = menuData.find(item => item.id === parseInt(foodId));
        if (!foodItem) return;

        const existing = cart.find(item => item.id === foodItem.id);
        if (existing) {
            existing.qty += 1;
        } else {
            cart.push({ ...foodItem, qty: 1 });
        }

        localStorage.setItem('ispice-cart', JSON.stringify(cart));
        if (sourceBtn) animateFlyToCart(sourceBtn);
        updateCartUI();
        showToast(`Added ${foodItem.name} to basket!`);
    }

    function updateCartUI() {
        const totalCount = cart.reduce((sum, item) => sum + item.qty, 0);
        if (cartCount) cartCount.textContent = totalCount;

        if (cart.length === 0) {
            if (cartEmpty) cartEmpty.style.display = 'block';
            if (cartFooter) cartFooter.style.display = 'none';
            const items = cartItemsList.querySelectorAll('.cart-item');
            items.forEach(el => el.remove());
            return;
        }

        if (cartEmpty) cartEmpty.style.display = 'none';
        if (cartFooter) cartFooter.style.display = 'block';

        const itemsHTML = cart.map(item => `
            <div class="cart-item" data-id="${item.id}">
                <img src="${item.image}" alt="${item.name}" class="cart-item-img">
                <div class="cart-item-info">
                    <h4>${item.name}</h4>
                    <span class="cart-item-price">$${(item.price * item.qty).toFixed(2)}</span>
                </div>
                <div class="cart-item-qty">
                    <button class="qty-btn dec-qty" data-id="${item.id}"><i data-lucide="minus"></i></button>
                    <span class="qty-val">${item.qty}</span>
                    <button class="qty-btn inc-qty" data-id="${item.id}"><i data-lucide="plus"></i></button>
                </div>
            </div>
        `).join('');

        cartItemsList.innerHTML = itemsHTML;
        if (typeof lucide !== 'undefined') lucide.createIcons();

        const subtotal = cart.reduce((sum, item) => sum + (item.price * item.qty), 0);
        if (cartSubtotal) cartSubtotal.textContent = `$${subtotal.toFixed(2)}`;
        if (cartTotal) cartTotal.textContent = `$${subtotal.toFixed(2)}`;

        cartItemsList.querySelectorAll('.inc-qty').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.getAttribute('data-id'));
                const item = cart.find(i => i.id === id);
                if (item) {
                    item.qty += 1;
                    localStorage.setItem('ispice-cart', JSON.stringify(cart));
                    updateCartUI();
                }
            });
        });

        cartItemsList.querySelectorAll('.dec-qty').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.getAttribute('data-id'));
                const item = cart.find(i => i.id === id);
                if (item) {
                    item.qty -= 1;
                    if (item.qty <= 0) cart = cart.filter(i => i.id !== id);
                    localStorage.setItem('ispice-cart', JSON.stringify(cart));
                    updateCartUI();
                }
            });
        });
    }

    document.addEventListener('click', (e) => {
        const addBtn = e.target.closest('.add-cart-btn');
        if (addBtn) {
            const id = addBtn.getAttribute('data-id');
            addToCart(id, addBtn);
        }
    });

    if (checkoutBtn) {
        checkoutBtn.addEventListener('click', () => {
            if (cart.length === 0) return;
            cart = [];
            localStorage.removeItem('ispice-cart');
            updateCartUI();
            toggleCart(false);
            showToast("Order placed successfully! Prepared in thermal packaging.", "success");
        });
    }

    // --- 8. QUICK VIEW FOOD DETAIL MODAL ---
    const foodModal = document.getElementById('foodModal');
    const closeFoodModalBtn = document.getElementById('closeFoodModalBtn');
    const foodModalContent = document.getElementById('foodModalContent');

    function openFoodModal(item) {
        if (!foodModal || !foodModalContent) return;

        foodModalContent.innerHTML = `
            <img src="${item.image}" alt="${item.name}" class="modal-food-img">
            <div class="modal-food-info">
                <h2>${item.name}</h2>
                <div class="modal-food-price">$${item.price.toFixed(2)}</div>
                <p class="modal-food-desc">${item.desc}</p>

                <div class="modal-tags">
                    ${item.tags.map(t => `<span class="modal-tag">${t}</span>`).join('')}
                </div>

                <button class="btn btn-primary btn-glow btn-block" id="modalAddToCartBtn" data-id="${item.id}">
                    <i data-lucide="plus"></i> Add to Order Basket
                </button>
            </div>
        `;

        foodModal.classList.add('active');
        if (typeof lucide !== 'undefined') lucide.createIcons();

        document.getElementById('modalAddToCartBtn').addEventListener('click', (e) => {
            addToCart(item.id, e.target);
            foodModal.classList.remove('active');
        });
    }

    if (closeFoodModalBtn) closeFoodModalBtn.addEventListener('click', () => foodModal.classList.remove('active'));
    if (foodModal) {
        foodModal.addEventListener('click', (e) => {
            if (e.target === foodModal) foodModal.classList.remove('active');
        });
    }

    // --- 9. AI TASTE CONCIERGE ENGINE ---
    const quizBox = document.getElementById('quizBox');
    const quizSteps = document.querySelectorAll('.quiz-step');
    const quizResult = document.getElementById('quizResult');
    const resultDishName = document.getElementById('resultDishName');
    const resultDishDesc = document.getElementById('resultDishDesc');
    const addResultToCart = document.getElementById('addResultToCart');
    const restartQuiz = document.getElementById('restartQuiz');

    let quizAnswers = {};
    let matchedItem = menuData[0];

    if (quizBox) {
        quizBox.addEventListener('click', (e) => {
            const optBtn = e.target.closest('.quiz-opt-ed');
            if (!optBtn) return;

            const key = optBtn.getAttribute('data-key');
            const val = optBtn.getAttribute('data-val');
            quizAnswers[key] = val;

            const currentStepEl = optBtn.closest('.quiz-step');
            const currentStepNum = parseInt(currentStepEl.getAttribute('data-quiz-step'));

            currentStepEl.classList.remove('active');

            if (currentStepNum < 3) {
                const nextStep = quizBox.querySelector(`[data-quiz-step="${currentStepNum + 1}"]`);
                if (nextStep) nextStep.classList.add('active');
            } else {
                if (quizAnswers.protein === 'vegan' || quizAnswers.flavor === 'fresh') {
                    matchedItem = menuData.find(i => i.id === 6) || menuData[0];
                } else if (quizAnswers.flavor === 'spicy') {
                    matchedItem = menuData.find(i => i.id === 2) || menuData[0];
                } else {
                    matchedItem = menuData.find(i => i.id === 1) || menuData[0];
                }

                if (resultDishName) resultDishName.textContent = matchedItem.name;
                if (resultDishDesc) resultDishDesc.textContent = matchedItem.desc;
                if (quizResult) quizResult.style.display = 'block';
            }
        });
    }

    if (addResultToCart) {
        addResultToCart.addEventListener('click', (e) => {
            addToCart(matchedItem.id, e.target);
            toggleCart(true);
        });
    }

    if (restartQuiz) {
        restartQuiz.addEventListener('click', () => {
            quizAnswers = {};
            if (quizResult) quizResult.style.display = 'none';
            quizSteps.forEach(s => s.classList.remove('active'));
            quizSteps[0].classList.add('active');
        });
    }

    // --- 10. TABLE RESERVATION MODAL ---
    const reserveModal = document.getElementById('reserveModal');
    const reservationBtn = document.getElementById('reservationBtn');
    const heroReserveBtn = document.getElementById('heroReserveBtn');
    const finalReserveBtn = document.getElementById('finalReserveBtn');
    const closeReserveBtn = document.getElementById('closeReserveBtn');
    const reserveForm = document.getElementById('reserveForm');

    function openReserveModal() {
        if (reserveModal) reserveModal.classList.add('active');
    }

    if (reservationBtn) reservationBtn.addEventListener('click', openReserveModal);
    if (heroReserveBtn) heroReserveBtn.addEventListener('click', openReserveModal);
    if (finalReserveBtn) finalReserveBtn.addEventListener('click', openReserveModal);
    if (closeReserveBtn) closeReserveBtn.addEventListener('click', () => reserveModal.classList.remove('active'));
    if (reserveModal) {
        reserveModal.addEventListener('click', (e) => {
            if (e.target === reserveModal) reserveModal.classList.remove('active');
        });
    }

    if (reserveForm) {
        reserveForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const refCode = "AURA-" + Math.floor(100000 + Math.random() * 900000);
            reserveModal.classList.remove('active');
            reserveForm.reset();
            showToast(`Table Reserved! Reference Code: ${refCode}`);
        });
    }

    // --- 11. NAVBAR SCROLLED CLASS ---
    const navbar = document.getElementById('navbar');
    window.addEventListener('scroll', () => {
        if (!navbar) return;
        if (window.scrollY > 50) navbar.classList.add('scrolled');
        else navbar.classList.remove('scrolled');
    });

    // --- 12. CUSTOM CURSOR DOT & RING ---
    const cursorDot = document.getElementById('cursorDot');
    const cursorRing = document.getElementById('cursorRing');

    if (cursorDot && cursorRing && window.innerWidth > 1024) {
        window.addEventListener('mousemove', (e) => {
            cursorDot.style.top = `${e.clientY}px`;
            cursorDot.style.left = `${e.clientX}px`;

            cursorRing.style.top = `${e.clientY}px`;
            cursorRing.style.left = `${e.clientX}px`;
        });

        document.querySelectorAll('a, button, .food-card-grid, .editorial-menu-row, .wall-item, .quiz-opt-ed').forEach(el => {
            el.addEventListener('mouseenter', () => {
                cursorRing.style.width = '55px';
                cursorRing.style.height = '55px';
                cursorRing.style.borderColor = 'var(--primary)';
            });
            el.addEventListener('mouseleave', () => {
                cursorRing.style.width = '36px';
                cursorRing.style.height = '36px';
                cursorRing.style.borderColor = 'var(--primary)';
            });
        });
    }

    // --- 13. TOAST NOTIFICATION ENGINE ---
    const toastContainer = document.getElementById('toastContainer');

    function showToast(message) {
        if (!toastContainer) return;
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.innerHTML = `<i data-lucide="check-circle-2"></i> <span>${message}</span>`;
        toastContainer.appendChild(toast);
        if (typeof lucide !== 'undefined') lucide.createIcons();

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(10px)';
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }
});
