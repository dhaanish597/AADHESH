# Aadesh Interactive 3D Construction Site Control Room

An isolated, interactive miniature 3D construction-site digital twin built for **Aadesh** (Environmental Compliance Execution Platform for Delhi-NCR construction sites).

This visual module is isolated inside `web/components/site-3d-lab/` and exposed via the sandbox route `/sandbox-3d`. It is designed to be embedded directly into the Supervisor Site Control Room dashboard without modifying any existing application routing, Cedar policies, or backend services.

---

## 1. How to Run the Prototype

### Prerequisites
- Node.js 18+ (tested with Node 20+)
- Python 3.13 (for local deterministic backend, optional for 3D standalone)

### Running Steps
1. Navigate to the `web/` directory and install dependencies (if not already installed):
   ```bash
   cd web
   npm install
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```

3. Open your browser and navigate to the isolated sandbox route:
   **[http://localhost:3000/sandbox-3d](http://localhost:3000/sandbox-3d)**

*(Optional)* Run the Python API in another shell:
```bash
.venv\Scripts\python -m aadesh_web.server --port 8787
```

---

## 2. Typed List of Selectable Scene Elements

All scene elements implement the data-driven `SiteElement` interface (`types.ts`):

| Element ID | Type | Display Name | Category / Floor | Presentation State | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `building-main` | `building` | Main Tower Block A | Superstructure | `verified` | Primary 5-story reinforced-concrete frame development in Delhi-NCR. |
| `floor-0` | `floor` | Level 0 Floor Slab | Structure / L0 | `verified` | Ground floor slab, paved perimeter, foundation perimeter. |
| `floor-1` | `floor` | Level 1 Floor Slab | Structure / L1 | `verified` | Commercial deck, curing structural columns. |
| `floor-2` | `floor` | Level 2 Floor Slab | Structure / L2 | `verified` | Residential slab, perimeter guard-rails installed. |
| `floor-3` | `floor` | Level 3 Floor Slab | Structure / L3 | `stale` | Upper shell, formwork erection, dust-suppression mist active. |
| `floor-4` | `floor` | Level 4 Floor Slab | Structure / L4 | `action_required` | Fresh pour active, curing mats deployed, wind monitor node active. |
| `crane-tower-1` | `crane` | Tower Crane TC-01 | Lifting Equipment | `verified` | Luffing tower crane with ultrasonic wind telemetry (<38 km/h). |
| `zone-piling` | `zone` | Piling & Foundation Sector | Foundation Drilling | `verified` | Bored cast-in-situ piling zone with slurry management. |
| `zone-demolition` | `zone` | Demolition & Crushing Bay | Structure Removal | `action_required` | Debris sorting; flagged for low dust mist nozzle pressure. |
| `zone-material` | `zone` | Material Staging & Batching | Storage & Transport | `stale` | Aggregate stockpiles; tarpaulin cover verification timestamp stale. |
| `zone-dust` | `zone` | Dust-Generating Work Zone | Cutting & Masonry | `action_required` | Enclosure curtains partially opened during active dry cutting. |
| `zone-access` | `zone` | Heavy Vehicle Gate & Wheel Wash | Access Logistics | `verified` | Automated high-pressure tire-washing bath prevents mud transfer. |
| `vehicle-tipper-1` | `vehicle` | Tipper Truck DL-1M-4820 | Material Transport | `verified` | 10-wheel heavy tipper carrying aggregate, BS-VI green pass verified. |
| `vehicle-excavator-1` | `vehicle` | Hydraulic Excavator EX-04 | Earthwork & Demolition | `action_required` | Crawler excavator operating in demolition bay; wet spray required. |
| `vehicle-sprinkler-1` | `vehicle` | Anti-Smog Mist Truck SM-02 | Dust Mitigation | `verified` | Mobile 5000L water tank truck with 360° turbine mist cannon. |

---

## 3. Asset Manifest & Strategy

Per **Prompt Section 3**, no heavy external 3D meshes (`.glb`/`.gltf`) were downloaded or bundled into the client build. The repository's `3d-assets/` directory contained only reference raster images (`construction.jpg`, `modular-construction-site-vol-3-3d-model-be3a2610fe.webp`, `tower.webp`).

All 3D models were crafted using **procedural low-poly Three.js geometry** with optimized instances and reused materials:
- **Building & Slabs**: Three.js `BoxGeometry`, `EdgesGeometry`, and `CylinderGeometry` rebar accents.
- **Tower Crane**: Procedural mast lattices, counter-jib, slewing cab, ballast blocks, hoist line, and hook block.
- **Work Zones**: Translucent bounded volumes with wireframe perimeter and safety bollards.
- **Vehicles**: Procedural cabs, chassis, wheels, excavator arm/bucket, and water mist canon.
- **Ground & Analytical Grid**: Precision analytical Drei `Grid` and layered asphalt/earth planes.

### Software Licenses
- `three`: MIT License
- `@react-three/fiber`: MIT License
- `@react-three/drei`: MIT License
- `@phosphor-icons/react`: MIT License

---

## 4. Integration Callback & Interface

The module is decoupled from backend API logic. It communicates selection events via the `onElementSelect` callback:

```tsx
import Site3DLab from '@/components/site-3d-lab/Site3DLab';
import { SiteElement } from '@/components/site-3d-lab/types';

export function SupervisorControlRoom() {
  const handleElementSelect = (element: SiteElement | null) => {
    if (!element) {
      console.log('Selection cleared');
      return;
    }
    
    console.log('Selected element ID:', element.id);
    console.log('Element type:', element.type);
    
    // Future Integration Layer:
    // Fetch verified obligations from the Aadesh Cedar/Corpus API:
    // fetch(`/api/obligations?sectorId=${element.id}`)
    //   .then(res => res.json())
    //   .then(data => updateSupervisorState(data));
  };

  return (
    <div className="w-full h-full">
      <Site3DLab onElementSelect={handleElementSelect} />
    </div>
  );
}
```

---

## 5. Architectural Safeguards & Features

1. **Client-Side Lazy Loading**: Dynamic import with `ssr: false` in `web/app/sandbox-3d/page.tsx` prevents Next.js SSR window/canvas errors.
2. **WebGL Fallback**: Built-in `isWebGLAvailable()` check automatically detects headless or unaccelerated clients and renders an accessible 2D schematic directory.
3. **React Error Boundary**: `CanvasErrorBoundary` encapsulates the R3F Canvas to prevent runtime graphics crashes from unmounting parent dashboard panels.
4. **Camera Navigation & Presets**: Smooth interpolated camera lerping with OrbitControls damping, preset views (`Overview`, `Tower Focus`, `Crane Focus`, `Reset`), and strict polar angle limits preventing camera clipping below ground.
5. **Exploded Floor View**: Interactive toggle expands floor slabs vertically (`L0` through `L4`) for clear unobstructed slab inspection.
6. **Keyboard / Screen Reader Accessibility**: Built-in accessible site roster modal lets users navigate and select elements without mouse/WebGL interaction.
7. **Restrained Visual Tone**: Concrete-900 / dark steel palette with clear color-blind safe status badges (`VERIFIED`, `ACTION REQUIRED`, `STALE`, `UNVERIFIED`) paired with descriptive text and icons.
