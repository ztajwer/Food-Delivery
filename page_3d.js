/* ==========================================================================
   ISPICE MAJESTY — STANDALONE PAGES 3D BACKGROUND ENGINE & THEME TOGGLE
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Lucide Icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // 2. Dark / Light Theme Toggle Engine
    const themeBtn = document.getElementById('themeToggleBtn');
    let currentTheme = localStorage.getItem('aura-theme') || 'dark';

    function applyTheme(theme) {
        currentTheme = theme;
        localStorage.setItem('aura-theme', theme);
        if (theme === 'light') {
            document.body.classList.remove('dark-theme');
            document.body.classList.add('light-theme');
        } else {
            document.body.classList.remove('light-theme');
            document.body.classList.add('dark-theme');
        }
    }

    applyTheme(currentTheme);

    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            const next = (currentTheme === 'dark') ? 'light' : 'dark';
            applyTheme(next);
        });
    }

    // 3. Floating 3D WebGL Canvas for Standalone Pages
    const canvasContainer = document.getElementById('page-3d-container');
    if (!canvasContainer || typeof THREE === 'undefined') return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 15;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    canvasContainer.appendChild(renderer.domElement);

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xff9d00, 1.5);
    dirLight1.position.set(10, 20, 15);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xff6a00, 1.2);
    dirLight2.position.set(-10, -10, -10);
    scene.add(dirLight2);

    // Floating 3D Objects Group
    const group = new THREE.Group();

    // 3D Object 1: Gold Torus Knot (Gourmet Ring Sculpture)
    const geometry1 = new THREE.TorusKnotGeometry(2.2, 0.6, 100, 16);
    const material1 = new THREE.MeshStandardMaterial({
        color: 0xff9d00,
        metalness: 0.85,
        roughness: 0.15,
        wireframe: false
    });
    const knot = new THREE.Mesh(geometry1, material1);
    knot.position.set(-8, 3, -2);
    group.add(knot);

    // 3D Object 2: Floating Icosahedron (Culinary Gem)
    const geometry2 = new THREE.IcosahedronGeometry(1.8, 1);
    const material2 = new THREE.MeshStandardMaterial({
        color: 0xff6a00,
        metalness: 0.7,
        roughness: 0.2,
        wireframe: true
    });
    const gem = new THREE.Mesh(geometry2, material2);
    gem.position.set(9, -4, -4);
    group.add(gem);

    // Floating Particles
    const particleCount = 120;
    const pGeometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount * 3; i += 3) {
        positions[i] = (Math.random() - 0.5) * 40;
        positions[i + 1] = (Math.random() - 0.5) * 40;
        positions[i + 2] = (Math.random() - 0.5) * 20;
    }

    pGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const pMaterial = new THREE.PointsMaterial({
        color: 0xff9d00,
        size: 0.15,
        transparent: true,
        opacity: 0.6
    });

    const particles = new THREE.Points(pGeometry, pMaterial);
    group.add(particles);

    scene.add(group);

    // Mouse Parallax Interaction
    let mouseX = 0, mouseY = 0;
    window.addEventListener('mousemove', (e) => {
        mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
        mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
    });

    // Animation Loop
    function animate() {
        requestAnimationFrame(animate);

        knot.rotation.x += 0.005;
        knot.rotation.y += 0.008;

        gem.rotation.x -= 0.006;
        gem.rotation.y += 0.004;

        particles.rotation.y += 0.001;

        group.rotation.y += (mouseX * 0.2 - group.rotation.y) * 0.05;
        group.rotation.x += (-mouseY * 0.2 - group.rotation.x) * 0.05;

        renderer.render(scene, camera);
    }

    animate();

    // Window Resize Handler
    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });
});
