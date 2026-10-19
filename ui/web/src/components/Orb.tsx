import { useEffect, useRef } from 'react';
import * as THREE from 'three';

import type { OrbState } from '../lib/types';

interface OrbProps {
  state: OrbState;
  accent: string;
  performance: boolean;
  reduceMotion: boolean;
  level?: number;
}

interface Preset {
  amp: number;
  speed: number;
  size: number;
  secondary: string;
}

const PRESETS: Record<OrbState, Preset> = {
  idle: { amp: 0.05, speed: 0.45, size: 1.0, secondary: '#e8f7ff' },
  listening: { amp: 0.15, speed: 1.15, size: 1.2, secondary: '#ffffff' },
  thinking: { amp: 0.09, speed: 2.1, size: 0.92, secondary: '#cfe9ff' },
  speaking: { amp: 0.19, speed: 1.5, size: 1.3, secondary: '#ffffff' },
  error: { amp: 0.27, speed: 3.0, size: 1.0, secondary: '#ff9aa9' },
};

const VERTEX_SHADER = /* glsl */ `
  attribute float aPhase;
  attribute float aScale;
  uniform float uTime;
  uniform float uAmp;
  uniform float uSize;
  uniform float uPixelRatio;
  varying float vGlow;

  void main() {
    vec3 p = position;
    float t = uTime;
    float wave = sin(t + aPhase) * 0.5 + sin(t * 1.7 + aPhase * 1.3) * 0.5;
    p += normalize(position) * wave * uAmp;

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = uSize * aScale * uPixelRatio * (2.6 / -mv.z);
    vGlow = 0.55 + 0.45 * wave;
  }
`;

const FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColorA;
  uniform vec3 uColorB;
  uniform float uOpacity;
  varying float vGlow;

  void main() {
    vec2 d = gl_PointCoord - vec2(0.5);
    float r = length(d);
    if (r > 0.5) discard;
    float alpha = smoothstep(0.5, 0.0, r);
    vec3 colour = mix(uColorA, uColorB, clamp(vGlow, 0.0, 1.0));
    gl_FragColor = vec4(colour, alpha * uOpacity * (0.35 + 0.65 * vGlow));
  }
`;

const TARGET_FPS = 30;
const DEGRADED_FPS = 20;

export function Orb({ state, accent, performance, reduceMotion, level = 0 }: OrbProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const uniformsRef = useRef<Record<string, THREE.IUniform> | null>(null);
  const stateRef = useRef<OrbState>(state);
  const levelRef = useRef(0);

  stateRef.current = state;
  levelRef.current = level;

  // Build the scene. Rebuilt only when the quality/accessibility profile changes.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) {
      return;
    }

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false });
    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, performance ? 1 : 1.5));
    renderer.domElement.className = 'orb__canvas';
    host.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.set(0, 0, 4.2);

    const count = performance ? 1500 : 4200;
    const positions = new Float32Array(count * 3);
    const phases = new Float32Array(count);
    const scales = new Float32Array(count);
    const golden = Math.PI * (3 - Math.sqrt(5));

    for (let i = 0; i < count; i += 1) {
      const y = 1 - (i / (count - 1)) * 2;
      const ring = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = golden * i;
      positions[i * 3] = Math.cos(theta) * ring * 1.55;
      positions[i * 3 + 1] = y * 1.55;
      positions[i * 3 + 2] = Math.sin(theta) * ring * 1.55;
      phases[i] = Math.random() * Math.PI * 2;
      scales[i] = 0.6 + Math.random() * 0.9;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('aPhase', new THREE.BufferAttribute(phases, 1));
    geometry.setAttribute('aScale', new THREE.BufferAttribute(scales, 1));

    const uniforms: Record<string, THREE.IUniform> = {
      uTime: { value: 0 },
      uAmp: { value: PRESETS[stateRef.current].amp },
      uSize: { value: PRESETS[stateRef.current].size },
      uPixelRatio: { value: renderer.getPixelRatio() },
      uColorA: { value: new THREE.Color(accent) },
      uColorB: { value: new THREE.Color(PRESETS[stateRef.current].secondary) },
      uOpacity: { value: 1 },
    };
    uniformsRef.current = uniforms;

    const material = new THREE.ShaderMaterial({
      uniforms,
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAGMENT_SHADER,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    const points = new THREE.Points(geometry, material);
    scene.add(points);

    const resize = () => {
      const width = host.clientWidth;
      const height = host.clientHeight;
      if (width === 0 || height === 0) {
        return;
      }
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();

    const observer = new ResizeObserver(resize);
    observer.observe(host);

    let frame = 0;
    let running = true;
    let last = window.performance.now();
    let accumulator = 0;
    let interval = 1000 / TARGET_FPS;
    let slowFrames = 0;
    let degraded = false;

    const renderFrame = (advance: number) => {
      const preset = PRESETS[stateRef.current];
      uniforms.uTime.value += advance;

      // Audio-reactive states modulate amplitude by the live microphone level.
      // Until a level arrives, fall back to a gentle synthetic pulse.
      let amp = preset.amp;
      if (stateRef.current === 'listening' || stateRef.current === 'speaking') {
        const live = levelRef.current;
        const level = live > 0 ? live : 0.5 + 0.5 * Math.sin(uniforms.uTime.value * 6.0);
        amp = preset.amp * (0.55 + 0.45 * level);
      }
      uniforms.uAmp.value = amp;

      renderer.render(scene, camera);
    };

    const tick = () => {
      if (!running) return;
      frame = window.requestAnimationFrame(tick);

      const now = window.performance.now();
      const delta = now - last;
      last = now;
      accumulator += delta;
      if (accumulator < interval) return;
      accumulator %= interval;

      // Frame-time watchdog: degrade rather than stutter.
      if (delta > 50) {
        slowFrames += 1;
      } else if (slowFrames > 0) {
        slowFrames -= 1;
      }
      if (!degraded && slowFrames > 120) {
        degraded = true;
        interval = 1000 / DEGRADED_FPS;
        renderer.setPixelRatio(1);
        uniforms.uPixelRatio.value = 1;
        resize();
      }

      renderFrame(interval / 1000);
    };

    if (reduceMotion) {
      renderFrame(0);
    } else {
      tick();
    }

    return () => {
      running = false;
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === host) {
        host.removeChild(renderer.domElement);
      }
      uniformsRef.current = null;
    };
  }, [accent, performance, reduceMotion]);

  // Reflect state changes on the existing material.
  useEffect(() => {
    const uniforms = uniformsRef.current;
    if (!uniforms) return;
    const preset = PRESETS[state];
    uniforms.uAmp.value = preset.amp;
    uniforms.uSize.value = preset.size;
    (uniforms.uColorB.value as THREE.Color).set(preset.secondary);
  }, [state]);

  return (
    <div className={`orb orb--${state}`}>
      <div className="orb__glow" />
      <div className="orb__ring orb__ring--a" />
      <div className="orb__ring orb__ring--b" />
      <div ref={hostRef} className="orb__canvas" />
      <div className="orb__hint">{state}</div>
    </div>
  );
}
