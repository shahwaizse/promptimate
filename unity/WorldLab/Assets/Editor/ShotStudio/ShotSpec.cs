// Resolved shot description that mcp_server/shots.py writes for the Unity side (JsonUtility-friendly, no dictionaries).
// Python does the high-level work (cast lookup, motion files, continue_from chains, staging); Unity builds the stage,
// samples the clips, computes the camera from the actual poses, renders and reports what ended up in frame.
using System;

namespace ShotStudio
{
    /// One clip on an actor's timeline. Chained clips (continue_from) arrive as consecutive segments, each already placed
    /// where the previous one ended (pos/yaw = where this clip's origin sits in the world).
    [Serializable] public class Seg
    {
        public string clip;             // Assets/... .kimodo (Humanoid AnimationClip sub-asset)
        public float start;             // shot time (s) at which this clip becomes active
        public float clipStart;         // time inside the clip at that moment
        public float speed = 1;
        public bool loop;
        public float[] pos = { 0, 0, 0 };
        public float yaw;               // degrees, Unity convention (clockwise seen from above)
        public bool place;              // later segments: snap to pos/yaw instead of carrying on with root motion
    }

    [Serializable] public class ActorSpec
    {
        public string id;
        public string model;            // Assets/... .fbx or .glb
        public string skin;             // optional albedo texture for the whole character (Kenney skins)
        public float height = 1.75f;    // standing height in metres
        public float build = 1;         // >1 widens the body (x/z scale) for a heavier build
        public float[] pos = { 0, 0, 0 }; // used when there are no segments (bind/idle pose stand-in)
        public float yaw;
        public Seg[] segs = new Seg[0];
        public bool footIK = true;
        public bool grounding = true;
        public float[] travelCal;       // [segment index, metric travel (m)] of the longest-travel clip: root motion is scaled to metres
        public PropSpec[] props = new PropSpec[0];
        public SeatSpec[] seats = new SeatSpec[0];
    }

    /// A prop held in one hand over a time range (see Props.cs for the grip frame). Python fills in the catalogue
    /// values (model, size, grip style, model orientation) from mcp_server/shots.py PROPS.
    [Serializable] public class PropSpec
    {
        public string id;
        public string model;            // Assets/... .glb/.fbx
        public string hand = "right";   // right|left
        public float start, end = 1e6f; // shot time range (s); hidden outside it
        public string grip = "power";   // power (fist round a handle) | flat (against the palm) | hang (bag) | cane | pinch
        public float size = 0.3f;       // longest dimension in metres, for a 1.75 m character (scaled with the actor)
        public float gripAt = 0.5f;     // where the hand holds it along the prop's main axis (0 = bottom, 1 = top)
        public float[] modelRot = { 0, 0, 0 }; // euler (deg) taking the model's main axis to +Y and its front to +Z
        public float[] offset = { 0, 0, 0 };   // extra offset in the grip frame (m): x thumb side, y out of the palm, z fingers
        public float[] rot = { 0, 0, 0 };      // extra rotation in the grip frame (deg)
        public string fingers = "grip"; // finger pose while held: grip|point|flat|fist|open|none
        public string light;            // "torch": a spot light along the prop's +Y (flashlight)
        public float[] tint;            // optional base colour multiplier (r,g,b)
    }

    /// The actor sits on a piece of furniture between start and end: the hips are eased onto the measured seat top
    /// (the generated motion already sits at about that height; this removes the last centimetres), feet stay planted.
    [Serializable] public class SeatSpec
    {
        public string furniture;        // FurnitureSpec id
        public float start, end;        // seated span (s, shot time)
        public float blend = 0.35f;     // ease in/out (s)
        public float maxCorrection = 0.15f; // metres; larger errors are reported, not hidden
    }

    /// Set dressing placed explicitly by the shot (benches, chairs, sofas, ledges, street lamps).
    [Serializable] public class FurnitureSpec
    {
        public string id;
        public string model;            // Assets/... .fbx (Kenney kits) or "box" for a plain ledge/block
        public string kit;              // kit-scale reference: Furniture | CityRoads | CitySuburban | "" (model units)
        public float scale = 1;         // extra uniform scale on top of the kit scale
        public float[] pos = { 0, 0, 0 };
        public float yaw;               // front of the piece faces this way (Unity yaw)
        public float stretch = 1;       // extra scale along the piece's width (a bench for two)
        public float seatHeight;        // >0: scale vertically so the seat top is exactly this high (within +-25 %)
        public float[] size;            // box: (x, y, z) metres
        public float[] color;           // box: (r, g, b)
        public float[] lamp;            // local (x, y, z) of a practical light head (street lamps)
        public string anchor = "center"; // center: pos is the footprint centre | pivot: the model's own origin
    }

    /// An extra light placed by the shot (shop sign, window, porch light).
    [Serializable] public class PracticalSpec
    {
        public float[] pos = { 0, 3, 0 };
        public float[] color = { 1f, 0.78f, 0.5f };
        public float intensity = 6, range = 8;
        public string type = "point";   // point|spot
        public float[] dir;             // spot direction (default straight down)
        public float angle = 100;
        public bool glow = true;        // visible emissive bulb
        public bool shadows;
    }

    [Serializable] public class CamSpec
    {
        public string preset = "medium"; // wide|medium|close_up|over_shoulder|follow|push_in|orbit|low_angle|top_down|two_shot|explicit
        public string subject;          // actor id (default: first actor)
        public string target;           // second actor id (over_shoulder: looks from subject toward target; two_shot)
        public string side = "auto";    // which side of the line of action: left|right|auto (keeps A screen-left)
        public float fov;               // vertical fov in degrees; 0 = preset default
        public float distance = 1;      // >1 pulls back, <1 pushes in
        public float height = -1;       // camera height override (m)
        public float yawOffset;         // extra rotation around the subject (deg)
        public float amount = 1;        // strength of moves (push/orbit/follow lag)
        public float[] pos, lookAt, endPos, endLookAt; // explicit camera
        public float orbitDeg;          // explicit orbit total degrees over the shot
        public string follow;           // explicit: actor id whose hips the look-at tracks
        public float handheld;          // 0..1 subtle camera noise (deterministic)
    }

    [Serializable] public class LightSpec
    {
        public string preset = "day";   // day|golden_hour|night_street|interior_warm|studio
        public float keyYaw = float.NaN; // fixed world yaw for the key light; NaN = relative to the camera
        public float exposure;          // extra post exposure (EV)
        public string weather = "";     // "" | rain | fog | rain_fog
        public float weatherAmount = 1; // 0..2
        public float rim = -1;          // >=0 overrides the look's rim light intensity
    }

    [Serializable] public class ShotSpec
    {
        public string id = "shot";
        public string outDir;
        public int width = 1080, height = 1920, fps = 30;
        public float seconds = 4;
        public float supersample = 1.5f;
        public string stage = "studio";
        public int seed;
        public LightSpec lighting = new LightSpec();
        public ActorSpec[] actors = new ActorSpec[0];
        public FurnitureSpec[] furniture = new FurnitureSpec[0];
        public PracticalSpec[] practicals = new PracticalSpec[0];
        public CamSpec camera = new CamSpec();
        public int reportEvery = 3;
        public string format = "png";   // png|jpg
    }
}
