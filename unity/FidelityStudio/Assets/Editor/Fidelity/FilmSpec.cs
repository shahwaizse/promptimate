// Film description written by demo/fidelity/make_film.py (JsonUtility-friendly). One continuous story clock: every
// shot is a camera over a time window of the same performance, so cuts stay continuous.
using System;

namespace Fidelity
{
    [Serializable] public class Seg
    {
        public string clip; public float start, clipStart, speed = 1; public bool loop;
        public float[] pos = { 0, 0, 0 }; public float yaw; public bool place;
    }

    [Serializable] public class SeatSpec
    {
        public string furniture; public float start, end; public float blend = 0.35f; public float maxCorrection = 0.12f;
    }

    /// A prop held in a hand from the start until `release`, then left where it was put (on the floor).
    [Serializable] public class PropSpec
    {
        public string model;            // Poly Haven model id
        public string part;             // optional: keep only child renderers whose name contains this
        public string hand = "right";
        public float release = 1e6f;    // story time it is put down
        public float size = 0.6f;       // longest side (m)
        public float[] gripLocal = { 0, 0, 0 }; // handle point in the (scaled) model's local frame
        public float[] rot = { 0, 0, 0 };       // model rotation so it hangs right (deg)
        public float carryUntil = -1;   // >0: the holding arm hangs straight (weight of the bag) until this time, eased out over carryBlend
        public float carryBlend = 0.55f;
    }

    [Serializable] public class ActorSpec
    {
        public string id; public string model; public float height = 1.75f;
        public float[] pos = { 0, 0, 0 }; public float yaw;
        public Seg[] segs = new Seg[0];
        public bool footIK = true; public bool grounding = true;
        public float[] travelCal;
        public SeatSpec[] seats = new SeatSpec[0];
        public PropSpec[] props = new PropSpec[0];
        public int blinkSeed = 1;
        public float headPitch = 18;    // degrees the head is tipped down after retargeting (see Film.HeadLevel)
        public ReachSpec[] reaches = new ReachSpec[0];
    }

    /// The hand picks up a chess piece and moves it: arm IK blends in toward the piece, carries it along an arc from
    /// `grab` to `place`, then blends back to the generated motion.
    [Serializable] public class ReachSpec
    {
        public string piece;            // node name in the chess set
        public string hand = "right";
        public float grab, place;       // story times
        public float blend = 0.6f;      // IK ease in/out (s)
        public float[] move = { 0, 0, 0.116f }; // offset in the chess set's local frame (m)
    }

    [Serializable] public class Key
    {
        public float t;                 // seconds from the shot start
        public float[] pos = { 0, 1.6f, -3 };
        public float[] look = { 0, 1.2f, 0 };
        public float focal = 35;        // mm on a 36x24 sensor
        public float focus = 3;         // focus distance (m); <=0: distance to the look-at point
        public float aperture = 2.8f;   // f-stop
        public float roll;
    }

    [Serializable] public class Shot
    {
        public string id; public float t0, t1;
        public Key[] keys = new Key[0];
        public float ev = 10;           // fixed exposure (EV100)
        public float handheld;          // 0..1
        public string ease = "smooth";  // smooth | linear
    }

    [Serializable] public class FilmSpec
    {
        public string outDir;
        public int width = 1920, height = 1080, fps = 24;
        public string mode = "pt";      // pt (path traced) | raster
        public int spp = 64;
        public float shutter = 0.5f;    // fraction of the frame interval the shutter is open (180 deg = 0.5)
        public string denoise = "oidn"; // oidn | none
        public int maxDepth = 6;
        public float sunElev = 14, sunAzim = 200, sunLux = 30000, sunKelvin = 3600, sunAngle = 0.6f;
        public string hdri = "ehingen_hillside_nosun_2k.hdr";
        public float skyLux = 9000, skyRot;
        public float fogMfp = 0;        // volumetric haze mean free path (m); 0 = off
        public bool dust = true;
        public ActorSpec[] actors = new ActorSpec[0];
        public Shot[] shots = new Shot[0];
        public string only = "";        // comma list of shot ids
        public int frameStep = 1;       // render every Nth frame (previews)
        public float[] frames;          // explicit story times to render as stills (overrides shots' frame list)
        public string stillsCam = "";   // shot id whose camera the stills use
        public bool layoutCheck;        // top-down + reference renders of the set
        public string format = "png";
    }
}
