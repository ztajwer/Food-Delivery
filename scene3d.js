/* ==========================================================================
   AURA 3D SCROLL & THREE.JS GASTRONOMY SCENE ENGINE (ORIGINAL EXHIBITION)
   ========================================================================== */

(function () {
    let container, scene, camera, renderer;
    let burgerGroup, burgerMotionGroup;
    let layerTopBun, layerLettuce, layerCheese, layerPatty, layerTomato, layerBottomBun, layerPlate;
    let particleSystem;
    let keyLight, fillLight, rimLight, ambientLight;
    let motionClock;

    let mouseX = 0, mouseY = 0;

    // Keep one canonical assembled state so every scroll chapter can return
    // the burger to the same place and orientation.
    const assembledLayers = {
        topBun: { x: 0, y: 0.95, z: 0 },
        lettuce: { x: 0, y: 0.65, z: 0 },
        cheese: { x: 0, y: 0.45, z: 0 },
        patty: { x: 0, y: 0.18, z: 0 },
        tomato: { x: 0, y: -0.10, z: 0 },
        bottomBun: { x: 0, y: -0.38, z: 0 },
        plate: { x: 0, y: -0.65, z: 0 }
    };

    const assembledBurger = {
        position: { x: 2.0, y: -0.2, z: 0.5 },
        rotation: { x: Math.PI / 12, y: -Math.PI / 6, z: 0 },
        scale: { x: 1, y: 1, z: 1 }
    };

    const desktopBurgerState = {
        position: { x: 2.0, y: -0.2, z: 0.5 },
        scale: 1
    };
    let compactViewport = false;

    function syncResponsiveBurgerState() {
        compactViewport = window.innerWidth <= 1024;
        const scale = compactViewport ? 0.45 : desktopBurgerState.scale;
        assembledBurger.position.x = compactViewport ? 0.0 : desktopBurgerState.position.x;
        assembledBurger.position.y = compactViewport ? -3.0 : desktopBurgerState.position.y;
        assembledBurger.position.z = compactViewport ? 0.0 : desktopBurgerState.position.z;
        assembledBurger.scale.x = scale;
        assembledBurger.scale.y = scale;
        assembledBurger.scale.z = scale;
    }

    function init3D() {
        container = document.getElementById('canvas-container');
        if (!container || typeof THREE === 'undefined') return;
        syncResponsiveBurgerState();

        // 1. Three.js Scene Setup
        scene = new THREE.Scene();
        scene.fog = new THREE.FogExp2(0x07080A, 0.03);

        // 2. Camera Setup
        camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
        camera.position.set(0, compactViewport ? 0.55 : 0.8, compactViewport ? 9.0 : 6.5);

        // 3. WebGL Renderer
        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.25;
        container.appendChild(renderer.domElement);
        motionClock = new THREE.Clock();

        // 4. Studio Lighting System
        ambientLight = new THREE.AmbientLight(0xfff5ea, 1.0);
        scene.add(ambientLight);

        keyLight = new THREE.DirectionalLight(0xffa200, 2.8);
        keyLight.position.set(5, 8, 5);
        keyLight.castShadow = true;
        keyLight.shadow.mapSize.width = compactViewport ? 1024 : 2048;
        keyLight.shadow.mapSize.height = compactViewport ? 1024 : 2048;
        scene.add(keyLight);

        fillLight = new THREE.DirectionalLight(0x0088ff, 0.7);
        fillLight.position.set(-5, 3, -5);
        scene.add(fillLight);

        rimLight = new THREE.PointLight(0xff6a00, 3.5, 12);
        rimLight.position.set(0, 4, -3);
        scene.add(rimLight);

        // 5. Construct Original 3D Burger Model & Floating Herbs
        createBurgerModel();
        createParticleAtmosphere();

        // 6. Event Listeners
        window.addEventListener('resize', onWindowResize, false);
        document.addEventListener('mousemove', onDocumentMouseMove, false);

        // 7. Setup GSAP ScrollTrigger Timelines
        setupScrollAnimations();

        // 8. Start Render Loop
        animate();
    }

    function createBurgerModel() {
        burgerGroup = new THREE.Group();

        // High-Quality PBR Materials
        const bunMaterial = new THREE.MeshStandardMaterial({
            color: 0xE28D38,
            roughness: 0.35,
            metalness: 0.08
        });

        const sesameMaterial = new THREE.MeshStandardMaterial({
            color: 0xFFF9EE,
            roughness: 0.25
        });

        const lettuceMaterial = new THREE.MeshStandardMaterial({
            color: 0x2EB85C,
            roughness: 0.35,
            side: THREE.DoubleSide
        });

        const cheeseMaterial = new THREE.MeshStandardMaterial({
            color: 0xFFB800,
            roughness: 0.2,
            metalness: 0.05
        });

        const pattyMaterial = new THREE.MeshStandardMaterial({
            color: 0x361E10,
            roughness: 0.7
        });

        const tomatoMaterial = new THREE.MeshStandardMaterial({
            color: 0xDC2626,
            roughness: 0.18
        });

        const plateMaterial = new THREE.MeshStandardMaterial({
            color: 0x161920,
            roughness: 0.2,
            metalness: 0.85
        });

        // --- LAYER 1: Top Brioche Bun & Sesame Seeds ---
        layerTopBun = new THREE.Group();
        const topBunGeo = new THREE.SphereGeometry(1.6, 32, 16, 0, Math.PI * 2, 0, Math.PI * 0.45);
        const topBunMesh = new THREE.Mesh(topBunGeo, bunMaterial);
        topBunMesh.scale.set(1, 0.7, 1);
        topBunMesh.castShadow = true;
        layerTopBun.add(topBunMesh);

        // 65 individual sesame seed meshes
        const sesameGeo = new THREE.SphereGeometry(0.055, 10, 8);
        for (let i = 0; i < 65; i++) {
            const seed = new THREE.Mesh(sesameGeo, sesameMaterial);
            const phi = Math.random() * Math.PI * 0.38;
            const theta = Math.random() * Math.PI * 2;
            const radius = 1.58;

            seed.position.x = radius * Math.sin(phi) * Math.cos(theta);
            seed.position.y = radius * Math.cos(phi) * 0.7;
            seed.position.z = radius * Math.sin(phi) * Math.sin(theta);
            seed.scale.set(0.65, 0.28, 1.25);
            seed.rotation.set(Math.random() * Math.PI, Math.random() * Math.PI, Math.random() * Math.PI);
            layerTopBun.add(seed);
        }
        layerTopBun.position.y = 0.95;

        // --- LAYER 2: Fresh Ruffled Lettuce ---
        layerLettuce = new THREE.Group();
        const lettuceGeo = new THREE.TorusGeometry(1.55, 0.22, 8, 40);
        const lettuceMesh = new THREE.Mesh(lettuceGeo, lettuceMaterial);
        lettuceMesh.scale.set(1.08, 0.28, 1);
        lettuceMesh.rotation.x = Math.PI / 2;
        lettuceMesh.castShadow = true;
        layerLettuce.add(lettuceMesh);
        for (let i = 0; i < 12; i++) {
            const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.34, 12, 8), lettuceMaterial);
            const angle = (i / 12) * Math.PI * 2;
            leaf.position.set(Math.cos(angle) * 1.53, 0, Math.sin(angle) * 1.35);
            leaf.scale.set(1.35, 0.18, 0.72);
            leaf.rotation.y = -angle;
            layerLettuce.add(leaf);
        }
        layerLettuce.position.y = 0.65;

        // --- LAYER 3: Melted Aged Cheddar Cheese ---
        layerCheese = new THREE.Group();
        const cheeseGeo = new THREE.BoxGeometry(2.35, 0.08, 2.35);
        const cheeseMesh = new THREE.Mesh(cheeseGeo, cheeseMaterial);
        cheeseMesh.rotation.y = Math.PI / 4;
        cheeseMesh.castShadow = true;
        layerCheese.add(cheeseMesh);
        layerCheese.position.y = 0.45;

        // --- LAYER 4: Prime A5 Wagyu Patty ---
        layerPatty = new THREE.Group();
        const pattyGeo = new THREE.CylinderGeometry(1.68, 1.72, 0.42, 32);
        const pattyMesh = new THREE.Mesh(pattyGeo, pattyMaterial);
        pattyMesh.castShadow = true;
        layerPatty.add(pattyMesh);
        layerPatty.position.y = 0.18;

        // --- LAYER 5: Sun-Ripened Heirloom Tomato ---
        layerTomato = new THREE.Group();
        const tomatoGeo = new THREE.CylinderGeometry(1.62, 1.62, 0.22, 32);
        const tomatoMesh = new THREE.Mesh(tomatoGeo, tomatoMaterial);
        tomatoMesh.castShadow = true;
        layerTomato.add(tomatoMesh);
        layerTomato.position.y = -0.10;

        // --- LAYER 6: Bottom Brioche Bun Heel ---
        layerBottomBun = new THREE.Group();
        const bottomBunGeo = new THREE.CylinderGeometry(1.58, 1.50, 0.38, 32);
        const bottomBunMesh = new THREE.Mesh(bottomBunGeo, bunMaterial);
        bottomBunMesh.castShadow = true;
        layerBottomBun.add(bottomBunMesh);
        layerBottomBun.position.y = -0.38;

        // --- LAYER 7: Marble Exhibition Display Plate ---
        layerPlate = new THREE.Group();
        const plateGeo = new THREE.CylinderGeometry(2.45, 1.85, 0.15, 48);
        const plateMesh = new THREE.Mesh(plateGeo, plateMaterial);
        plateMesh.receiveShadow = true;
        layerPlate.add(plateMesh);
        layerPlate.position.y = -0.65;

        // Assembly
        burgerGroup.add(layerTopBun);
        burgerGroup.add(layerLettuce);
        burgerGroup.add(layerCheese);
        burgerGroup.add(layerPatty);
        burgerGroup.add(layerTomato);
        burgerGroup.add(layerBottomBun);
        burgerGroup.add(layerPlate);

        burgerGroup.position.set(
            assembledBurger.position.x,
            assembledBurger.position.y,
            assembledBurger.position.z
        );
        burgerGroup.rotation.set(
            assembledBurger.rotation.x,
            assembledBurger.rotation.y,
            assembledBurger.rotation.z
        );

        // Keep ambient motion on a parent group. ScrollTrigger owns burgerGroup,
        // so user motion can never fight or overwrite the scroll choreography.
        burgerMotionGroup = new THREE.Group();
        burgerMotionGroup.add(burgerGroup);
        scene.add(burgerMotionGroup);
    }

    function createParticleAtmosphere() {
        const particleCount = 220;
        const geometry = new THREE.BufferGeometry();
        const positions = new Float32Array(particleCount * 3);
        const colors = new Float32Array(particleCount * 3);

        const colorGold = new THREE.Color(0xFF9D00);
        const colorAmber = new THREE.Color(0xFF6A00);
        const colorGreen = new THREE.Color(0x2EB85C);

        for (let i = 0; i < particleCount; i++) {
            positions[i * 3] = (Math.random() - 0.5) * 20;
            positions[i * 3 + 1] = (Math.random() - 0.5) * 20;
            positions[i * 3 + 2] = (Math.random() - 0.5) * 20;

            const rand = Math.random();
            const mixedColor = rand > 0.6 ? colorGold : (rand > 0.3 ? colorAmber : colorGreen);
            colors[i * 3] = mixedColor.r;
            colors[i * 3 + 1] = mixedColor.g;
            colors[i * 3 + 2] = mixedColor.b;
        }

        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const material = new THREE.PointsMaterial({
            size: 0.09,
            vertexColors: true,
            transparent: true,
            opacity: 0.7,
            blending: THREE.AdditiveBlending
        });

        particleSystem = new THREE.Points(geometry, material);
        scene.add(particleSystem);
    }

    // Dynamic Theme Adjustment for 3D Canvas
    window.update3DTheme = function (isLight) {
        if (!scene) return;

        if (isLight) {
            scene.fog.color.setHex(0xF8FAFC);
            if (ambientLight) ambientLight.intensity = 1.6;
            if (keyLight) keyLight.intensity = 3.2;
        } else {
            scene.fog.color.setHex(0x07080A);
            if (ambientLight) ambientLight.intensity = 1.0;
            if (keyLight) keyLight.intensity = 2.8;
        }
    };

    // ScrollTrigger GSAP Timelines for Chapters
    function setupScrollAnimations() {
        if (typeof gsap === 'undefined' || typeof ScrollTrigger === 'undefined') return;
        gsap.registerPlugin(ScrollTrigger);

        function restoreAssembledState() {
            gsap.set([
                layerTopBun.position,
                layerLettuce.position,
                layerCheese.position,
                layerPatty.position,
                layerTomato.position,
                layerBottomBun.position,
                layerPlate.position
            ], { x: 0, z: 0 });
            gsap.set(layerTopBun.position, assembledLayers.topBun);
            gsap.set(layerLettuce.position, assembledLayers.lettuce);
            gsap.set(layerCheese.position, assembledLayers.cheese);
            gsap.set(layerPatty.position, assembledLayers.patty);
            gsap.set(layerTomato.position, assembledLayers.tomato);
            gsap.set(layerBottomBun.position, assembledLayers.bottomBun);
            gsap.set(layerPlate.position, assembledLayers.plate);
            gsap.set(burgerGroup.position, assembledBurger.position);
            gsap.set(burgerGroup.rotation, assembledBurger.rotation);
            gsap.set(burgerGroup.scale, assembledBurger.scale);
            gsap.set(camera.position, { x: 0, y: compactViewport ? 0.55 : 0.8, z: compactViewport ? 9.0 : 6.5 });
        }

        // Re-entering the hero from any later chapter must always produce the
        // same complete burger, camera framing, and starting orientation.
        ScrollTrigger.create({
            trigger: '#hero',
            start: 'top top',
            onEnter: restoreAssembledState,
            onEnterBack: restoreAssembledState
        });

        // Timeline 1: Chapter 01 -> 02 (The Craft)
        const craftTL = gsap.timeline({
            scrollTrigger: {
                trigger: "#craft",
                start: "top 80%",
                end: "bottom 20%",
                scrub: 1
            }
        });

        craftTL
            .to(burgerGroup.position, { x: compactViewport ? 0.2 : 0, y: compactViewport ? -0.35 : 0, z: compactViewport ? 2.7 : 2.2 }, 0)
            .to(burgerGroup.scale, { x: compactViewport ? 0.62 : 1.35, y: compactViewport ? 0.62 : 1.35, z: compactViewport ? 0.62 : 1.35 }, 0)
            .to(burgerGroup.rotation, { x: Math.PI / 10, y: Math.PI * 0.5 }, 0);

        // Timeline 2: Chapter 03 (SIGNATURE ZOOM THROUGH FOOD)
        const zoomTL = gsap.timeline({
            scrollTrigger: {
                trigger: "#zoom-through",
                start: "top top",
                end: "+=2000",
                pin: true,
                scrub: 1,
                onUpdate: (self) => {
                    updateZoomThroughOverlays(self.progress);
                }
            }
        });

        zoomTL
            .to(layerTopBun.position, { y: 2.5 }, 0)
            .to(layerLettuce.position, { y: 1.6 }, 0)
            .to(layerCheese.position, { y: 0.7 }, 0)
            .to(layerPatty.position, { y: -0.2 }, 0)
            .to(layerTomato.position, { y: -1.1 }, 0)
            .to(layerBottomBun.position, { y: -1.9 }, 0)
            .to(layerPlate.position, { y: -2.6 }, 0)
            .to(camera.position, { z: compactViewport ? 6.2 : 4.2, y: compactViewport ? 0.3 : 0 }, 0)
            .to(burgerGroup.position, { x: compactViewport ? 0.9 : 1.5, y: compactViewport ? -0.35 : 0, z: 0 }, 0)
            .to(burgerGroup.rotation, { x: 0, y: Math.PI * 1.2 }, 0);

        // Timeline 3: Chapter 04 (Ingredient Wall)
        const wallTL = gsap.timeline({
            scrollTrigger: {
                trigger: "#ingredient-wall",
                start: "top 80%",
                end: "bottom 20%",
                scrub: 1
            }
        });

        wallTL
            .to(camera.position, { z: compactViewport ? 7.2 : 5.5, y: compactViewport ? 0.45 : 0.5 }, 0)
            .to(burgerGroup.position, { x: compactViewport ? 1.1 : 1.8, y: compactViewport ? -0.35 : 0, z: 0 }, 0)
            .to(layerTopBun.position, { x: 0.8, y: 1.5 }, 0)
            .to(layerLettuce.position, { x: 1.4, y: 0.8 }, 0)
            .to(layerCheese.position, { x: 2.0, y: 0.1 }, 0)
            .to(layerPatty.position, { x: 2.6, y: -0.6 }, 0)
            .to(burgerGroup.rotation, { x: 0.2, y: Math.PI * 0.4 }, 0);

        // Timeline 4: Chapter 05 (Menu Reconstruction)
        const menuTL = gsap.timeline({
            scrollTrigger: {
                trigger: "#menu",
                start: "top 80%",
                end: "top 20%",
                scrub: 1
            }
        });

        menuTL
            .to(layerTopBun.position, assembledLayers.topBun, 0)
            .to(layerLettuce.position, assembledLayers.lettuce, 0)
            .to(layerCheese.position, assembledLayers.cheese, 0)
            .to(layerPatty.position, assembledLayers.patty, 0)
            .to(layerTomato.position, assembledLayers.tomato, 0)
            .to(layerBottomBun.position, assembledLayers.bottomBun, 0)
            .to(layerPlate.position, assembledLayers.plate, 0)
            .to(burgerGroup.position, assembledBurger.position, 0)
            .to(burgerGroup.scale, assembledBurger.scale, 0)
            .to(burgerGroup.rotation, assembledBurger.rotation, 0);

        // Timeline 5: Chapter 06 (Quiz & Reviews)
        const quizTL = gsap.timeline({
            scrollTrigger: {
                trigger: "#quiz",
                start: "top 80%",
                end: "bottom 20%",
                scrub: 1
            }
        });

        quizTL
            .to(burgerGroup.position, { x: -6.0, y: -1.0, z: -3.0 }, 0)
            .to(burgerGroup.scale, { x: compactViewport ? 0.34 : 0.5, y: compactViewport ? 0.34 : 0.5, z: compactViewport ? 0.34 : 0.5 }, 0);
    }

    function updateZoomThroughOverlays(progress) {
        const infos = [
            document.getElementById('infoBun'),
            document.getElementById('infoLettuce'),
            document.getElementById('infoCheese'),
            document.getElementById('infoPatty'),
            document.getElementById('infoTomato')
        ];

        infos.forEach(info => info && info.classList.remove('active'));

        if (progress > 0.05 && progress <= 0.25 && infos[0]) infos[0].classList.add('active');
        else if (progress > 0.25 && progress <= 0.45 && infos[1]) infos[1].classList.add('active');
        else if (progress > 0.45 && progress <= 0.65 && infos[2]) infos[2].classList.add('active');
        else if (progress > 0.65 && progress <= 0.85 && infos[3]) infos[3].classList.add('active');
        else if (progress > 0.85 && infos[4]) infos[4].classList.add('active');
    }

    function onWindowResize() {
        if (!camera || !renderer) return;
        const previousCompactViewport = compactViewport;
        syncResponsiveBurgerState();
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);

        if (previousCompactViewport !== compactViewport && burgerGroup) {
            gsap.set(burgerGroup.position, assembledBurger.position);
            gsap.set(burgerGroup.scale, assembledBurger.scale);
            gsap.set(camera.position, { x: 0, y: compactViewport ? 0.55 : 0.8, z: compactViewport ? 9.0 : 6.5 });
        }
    }

    function onDocumentMouseMove(event) {
        mouseX = (event.clientX - window.innerWidth / 2) * 0.0005;
        mouseY = (event.clientY - window.innerHeight / 2) * 0.0005;
    }

    function animate() {
        requestAnimationFrame(animate);

        if (burgerMotionGroup) {
            const elapsed = motionClock ? motionClock.getElapsedTime() : 0;

            // Bounded motion keeps the burger floating without accumulating
            // rotation and drifting away from its assembled home position.
            burgerMotionGroup.rotation.y = Math.sin(elapsed * 0.55) * 0.05;
            const mouseTilt = mouseY * 0.12;
            const floatTilt = Math.sin(elapsed * 0.4) * 0.018;
            burgerMotionGroup.rotation.x += (mouseTilt + floatTilt - burgerMotionGroup.rotation.x) * 0.035;
        }

        if (particleSystem) {
            particleSystem.rotation.y += 0.0005;
        }

        renderer.render(scene, camera);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init3D);
    } else {
        init3D();
    }
})();
