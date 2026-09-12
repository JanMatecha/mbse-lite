import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

globalThis.mbseThreeModules = Object.freeze({
  THREE,
  GLTFLoader,
  OrbitControls
});
