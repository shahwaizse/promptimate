// Resolved world description written by mcp_server/world.py (JsonUtility-friendly: arrays, no dictionaries).
// Python does the high-level work (asset choice, layout solver, physically based light values, cameras); Unity builds
// the room, snaps every model onto the floor / wall / surface it belongs to using its real mesh bounds, lights it,
// renders stills and a camera move, and reports what actually ended up where (for automatic validation).
using System;

namespace WorldLab
{
    [Serializable] public class OpeningSpec
    {
        public string type = "window";   // window | door | arch | tunnel
        public float u;                  // centre along the wall, metres from the wall's start point a
        public float width = 1.2f, height = 1.4f, sill = 0.9f;
        public bool glass = true;
        public bool blinds;              // venetian blinds (real slats: they cast real striped shadows)
        public float blindsTilt = 35;    // slat tilt in degrees
        public float blindsOpen = 1;     // 1 = fully down
        public bool curtains;
        public string curtainMat = "";
        public float[] frameColor = { 0.85f, 0.83f, 0.78f };
        public bool rainy;               // rain running down the glass
        public float doorOpen;           // door leaf swing (degrees)
        public float[] doorColor = { 0.35f, 0.24f, 0.16f };
        public string doorMat = "";
    }

    [Serializable] public class WallSpec
    {
        public string name;
        public float[] a, b;             // x,z endpoints on the room boundary
        public float[] n;                // inward normal (x,z)
        public string mat;
        public float[] tint;
        public float height = 2.8f;
        public float baseY;              // bottom of the wall (trench walls go below 0)
        public OpeningSpec[] openings = new OpeningSpec[0];
        public bool baseboard = true;
    }

    [Serializable] public class FeatureSpec
    {
        public string type;              // column | trench | strip | box | rail | sign
        public float[] pos = { 0, 0, 0 };
        public float[] size = { 0.4f, 2.8f, 0.4f };
        public float yaw;
        public string mat = "";
        public float[] color;
        public float emissive;           // >0: self-lit (signs, light strips)
        public string text = "";
    }

    [Serializable] public class RoomSpec
    {
        public float w = 5, d = 4, h = 2.8f;
        public string floorMat, ceilingMat;
        public float[] floorTint, ceilingTint;
        public float[] trimColor = { 0.9f, 0.88f, 0.84f };
        public bool ceiling = true;
        public FeatureSpec[] features = new FeatureSpec[0];
        public float[] floorRect;        // x0,z0,x1,z1 of the walkable floor (default the whole room)
    }

    [Serializable] public class MatSpec
    {
        public string id;
        public string albedo, normal, rough;  // Assets/... paths
        public float tile = 2;           // metres per texture repeat
        public float smooth = 0.3f, metallic;
        public float[] tint;
        public float normalScale = 1;
    }

    [Serializable] public class ItemSpec
    {
        public string id;
        public string asset;             // library id (world_assets.json)
        public string path;              // Assets/... model; empty for procedural
        public string src;               // polyhaven | kenney | quaternius | procedural
        public string proc;              // procedural kind: ashtray | rug | curtain | box | mug | paper | poster | cylinder
        public float[] pos = { 0, 0, 0 };
        public float yaw;
        public float front;              // model's own front correction (deg)
        public float scale = 1;
        public float fitHeight;          // >0: uniform scale so the mesh is this tall
        public string anchor = "floor";  // floor | wall | surface | ceiling | seat | free
        public float[] wallN;            // wall anchor: inward normal (x,z)
        public float wallD;              // wall anchor: plane offset (n . p = wallD at the wall surface)
        public float mountY = -1;        // wall anchor: height of the item's centre
        public string on = "";           // surface/seat anchor: parent id (dropped onto its top by ray cast)
        public float[] size;             // procedural size (x,y,z)
        public string mat = "";          // procedural material id
        public float[] color;            // procedural / tint colour
        public float[] tint;
        public float emissive;
        public bool shadows = true;
        public bool lie;                 // lies flat (papers): drop with a small random rotation only
    }

    [Serializable] public class LightItem
    {
        public string id;
        public string type = "point";    // directional | point | spot
        public float[] pos = { 0, 2, 0 };
        public float[] dir = { 0, -1, 0 };
        public float[] color = { 1, 1, 1 };
        public float intensity = 1, range = 6, angle = 90, inner = 60;
        public bool shadows;
        public float flicker;            // 0..1 deterministic intensity noise
        public string glow = "";         // bulb | flame | none
        public float glowSize = 0.05f;
        public float glowIntensity = 6;
        public string attach = "";       // item id: pos is an offset from the item's bottom centre in its own frame
        public string role = "";         // key | fill | bounce | practical | sun | moon | street | lightning | ambient
    }

    [Serializable] public class EnvSpec
    {
        public string hdri = "";         // Assets/... .hdr (window view + reflections)
        public float hdriExposure = 1, hdriRotation;
        public float[] skyColor = { 0.05f, 0.06f, 0.09f }; // when there is no HDRI
        public float[] ambientSky = { 0.1f, 0.1f, 0.12f }, ambientEquator = { 0.08f, 0.08f, 0.09f }, ambientGround = { 0.05f, 0.04f, 0.04f };
        public float reflection = 0.5f;
        public float fogDensity;
        public float[] fogColor = { 0.2f, 0.2f, 0.22f };
    }

    [Serializable] public class PostSpec
    {
        public float exposure, contrast = 8, saturation, temperature, tint;
        public float bloom = 0.4f, bloomThreshold = 1, vignette = 0.25f, grain = 0.12f;
        public float[] shadowsTint = { 1, 1, 1, 0 }, highlightsTint = { 1, 1, 1, 0 };
        public float dof;                // >0: aperture-like strength
        public float ssao = 1.2f;
    }

    [Serializable] public class EffectSpec
    {
        public string type;              // smoke | dust | shaft | rain_outside | snow_outside | lightning | steam | rain_glass
        public float[] pos = { 0, 0, 0 };
        public float[] size = { 1, 1, 1 };
        public float[] dir = { 0, -1, 0 };
        public float[] axis;             // shaft: the window's horizontal axis
        public float[] color = { 1, 1, 1 };
        public float amount = 1;
        public string target = "";       // item id (smoke source etc.)
        public float[] times;            // lightning flash times (s)
    }

    [Serializable] public class CamShot
    {
        public string name = "still";
        public float[] pos = { 0, 1.5f, -2 };
        public float[] look = { 0, 1, 0 };
        public float fov = 55;
        public float t;                  // effect time to render the still at
    }

    [Serializable] public class CamMove
    {
        public string name = "move";
        public float[] pos0, look0, pos1, look1;
        public float fov0 = 55, fov1 = 55;
        public float seconds;            // 0 = no move
        public int fps = 30;
    }

    [Serializable] public class WorldJob
    {
        public string kind = "world";    // world | measure
        public string id = "world";
        public string outDir;
        public int seed;
        public int width = 1920, height = 1080;
        public float supersample = 1.5f;
        public RoomSpec room = new RoomSpec();
        public WallSpec[] walls = new WallSpec[0];
        public MatSpec[] materials = new MatSpec[0];
        public ItemSpec[] items = new ItemSpec[0];
        public LightItem[] lights = new LightItem[0];
        public EnvSpec env = new EnvSpec();
        public PostSpec post = new PostSpec();
        public EffectSpec[] effects = new EffectSpec[0];
        public CamShot[] stills = new CamShot[0];
        public CamMove move = new CamMove();
        public bool lineup;              // measure job: also render a front-view lineup of the models
        public string[] hdris = new string[0]; // measure job: HDRIs whose mean radiance to measure
    }
}
