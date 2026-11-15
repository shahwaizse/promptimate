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
        public float[] pos = { 0, 0, 0 }; // used when there are no segments (bind/idle pose stand-in)
        public float yaw;
        public Seg[] segs = new Seg[0];
        public bool footIK = true;
        public bool grounding = true;
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
        public CamSpec camera = new CamSpec();
        public int reportEvery = 3;
        public string format = "png";   // png|jpg
    }
}
