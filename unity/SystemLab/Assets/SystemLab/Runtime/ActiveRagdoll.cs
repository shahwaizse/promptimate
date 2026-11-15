// Active ragdoll: rigidbodies + ConfigurableJoints on a Humanoid rig. Joint slerp drives ("muscles") track the local
// rotations of an invisible kinematic copy that plays Promptimate clips (MotionTrack); a balance assist ("hand of
// god" pins on every body part) keeps it upright while nothing happens. Hits make the struck region go limp and cost
// balance; losing balance drops the assist and most muscle tone, the arms brace toward the fall, and once the body
// lies still a Promptimate get-up clip is aligned to it and the muscles and assist ramp back in.
//
// Stepped manually: call PreStep(dt) for every ragdoll, Physics.Simulate(dt), then PostStep(dt).
using System.Collections.Generic;
using UnityEngine;

namespace SystemLab
{
    public enum RagdollState { Puppet, Falling, Lying, GettingUp }

    public class ActiveRagdoll
    {
        public class Part
        {
            public HumanBodyBones bone;
            public string kind;     // hips spine chest head upperArm lowerArm upperLeg lowerLeg foot
            public string region;   // core spine neck arms legs
            public bool left;
            public Transform t, target;
            public Rigidbody rb;
            public ConfigurableJoint joint;
            public Part parent;
            public Quaternion startLocal;       // inv(parent.rot) * rot in the bind pose
            public Quaternion w2j, j2w;         // joint space conversion
            public Vector3 boneDirLocal;        // bind bone direction (to the child joint) in local space
            public Vector3 fwdLocal;            // the character's forward direction in this part's local space (bind)
            public float baseSpring, pinGain;
            public float local = 1f;            // hit limpness multiplier (recovers to 1)
            public Vector3 prevTargetPos; public Quaternion prevTargetRot;
            public Vector3 targetVel;
            public List<Collider> cols = new List<Collider>();
            public bool grounded;
            public float lastHit = -99f;
        }

        // ---- configuration ----
        public static int Layer = 8;            // every ragdoll body; layer 9 = kinematic comparison bodies
        public const float PinKp = 900f, PinKd = 50f, PinMaxAcc = 90f;
        public const float HipKpA = 700f, HipKdA = 45f;
        /// Sign between a child rotation of +a degrees about the joint axis (Quaternion.AngleAxis) and the angle the
        /// joint reports for its X limits. Measured by LabTests.JointSign.
        public static float JointSign = -1f;

        public readonly string id;
        public readonly GameObject go;          // visible, simulated character
        public readonly MotionTrack track;      // invisible target
        public Personality p;
        public readonly bool kinematic;         // comparison mode: bodies follow the animation, no reactions
        public readonly List<Part> parts = new List<Part>();
        readonly Dictionary<int, Part> byBody = new Dictionary<int, Part>();
        readonly Dictionary<HumanBodyBones, Part> byBone = new Dictionary<HumanBodyBones, Part>();
        public Part hips => parts[0];
        public float totalMass;
        public float scale = 1f;

        // ---- state ----
        public RagdollState state = RagdollState.Puppet;
        public float stateTime;
        public float pin = 1f;                  // current balance assist (scaled by personality.balance)
        public float tone = 1f;                 // global muscle tone
        float lastHitTime = -99f, simTime;
        float recentDv, recentT;   // hits within ~0.3 s add up (a shove is many contact steps)
        float unsupported;
        float stillTime;
        Vector3 fallDir;
        public float anticipationBoost = 1f;
        public System.Func<ActiveRagdoll, (AnimationClip clip, float start)> chooseGetUp;
        public AnimationClip afterGetUp; public bool afterGetUpLoop = true;
        float getUpStart;
        public readonly List<string> log = new List<string>();
        public readonly HashSet<int> obstacleColliders;   // shared: static colliders that trip / hit (not floors)
        public System.Func<Vector3, float> groundAt;       // ground height under a point

        // ---- metrics ----
        public double trackPosErrSum, trackAngErrSum; public int trackSamples; public float trackPosErrMax;
        public float maxAngVel, maxLinVel; public int nanCount; public double lyingSpeedSqSum; public int lyingSamples;

        public ActiveRagdoll(string id, GameObject visible, GameObject target, Personality personality, bool kinematic,
                             HashSet<int> obstacles)
        {
            this.id = id; go = visible; p = personality; this.kinematic = kinematic; obstacleColliders = obstacles;
            track = new MotionTrack(target);
            var va = visible.GetComponent<Animator>();
            Build(va, track.anim);
            va.enabled = false; // the physics owns the visible bones from now on
            foreach (var r in target.GetComponentsInChildren<Renderer>()) r.enabled = false;
        }

        // ------------------------------------------------------------------ build
        static readonly (HumanBodyBones b, HumanBodyBones parent, string kind, string region, float mass)[] Spec =
        {
            (HumanBodyBones.Hips, HumanBodyBones.LastBone, "hips", "core", 0.15f),
            (HumanBodyBones.Spine, HumanBodyBones.Hips, "spine", "spine", 0.13f),
            (HumanBodyBones.UpperChest, HumanBodyBones.Spine, "chest", "spine", 0.17f),
            (HumanBodyBones.Head, HumanBodyBones.UpperChest, "head", "neck", 0.07f),
            (HumanBodyBones.LeftUpperArm, HumanBodyBones.UpperChest, "upperArm", "arms", 0.03f),
            (HumanBodyBones.LeftLowerArm, HumanBodyBones.LeftUpperArm, "lowerArm", "arms", 0.025f),
            (HumanBodyBones.RightUpperArm, HumanBodyBones.UpperChest, "upperArm", "arms", 0.03f),
            (HumanBodyBones.RightLowerArm, HumanBodyBones.RightUpperArm, "lowerArm", "arms", 0.025f),
            (HumanBodyBones.LeftUpperLeg, HumanBodyBones.Hips, "upperLeg", "legs", 0.11f),
            (HumanBodyBones.LeftLowerLeg, HumanBodyBones.LeftUpperLeg, "lowerLeg", "legs", 0.05f),
            (HumanBodyBones.LeftFoot, HumanBodyBones.LeftLowerLeg, "foot", "legs", 0.015f),
            (HumanBodyBones.RightUpperLeg, HumanBodyBones.Hips, "upperLeg", "legs", 0.11f),
            (HumanBodyBones.RightLowerLeg, HumanBodyBones.RightUpperLeg, "lowerLeg", "legs", 0.05f),
            (HumanBodyBones.RightFoot, HumanBodyBones.RightLowerLeg, "foot", "legs", 0.015f),
        };

        static readonly Dictionary<string, float> BaseSpring = new Dictionary<string, float>
        {
            {"spine", 1100}, {"chest", 800}, {"head", 140}, {"upperArm", 200}, {"lowerArm", 90},
            {"upperLeg", 1300}, {"lowerLeg", 900}, {"foot", 220},
        };
        static readonly Dictionary<string, float> PinGain = new Dictionary<string, float>
        {
            {"hips", 1f}, {"spine", 0.7f}, {"chest", 0.7f}, {"head", 0f}, {"upperArm", 0f}, {"lowerArm", 0f},
            {"upperLeg", 0.5f}, {"lowerLeg", 0.5f}, {"foot", 0.6f},
        };

        static Transform Bone(Animator a, HumanBodyBones b)
        {
            var t = a.GetBoneTransform(b);
            if (!t && b == HumanBodyBones.UpperChest) t = a.GetBoneTransform(HumanBodyBones.Chest);
            return t;
        }

        void Build(Animator va, Animator ta)
        {
            var root = go.transform;
            Vector3 fwd = root.forward, right = root.right, up = Vector3.up;
            var head = Bone(va, HumanBodyBones.Head);
            float groundY = root.position.y;
            scale = Mathf.Max(0.3f, (head.position.y - groundY) / 1.55f);
            float s = scale;
            totalMass = 72f * s * s * s;
            var mat = new PhysicsMaterial("body") { dynamicFriction = 0.8f, staticFriction = 0.9f, bounciness = 0f,
                frictionCombine = PhysicsMaterialCombine.Average, bounceCombine = PhysicsMaterialCombine.Minimum };

            Vector3 P(HumanBodyBones b) => Bone(va, b).position;
            float shoulderW = Vector3.Distance(P(HumanBodyBones.LeftUpperArm), P(HumanBodyBones.RightUpperArm));
            float hipW = Vector3.Distance(P(HumanBodyBones.LeftUpperLeg), P(HumanBodyBones.RightUpperLeg));

            foreach (var sp in Spec)
            {
                var t = Bone(va, sp.b);
                var part = new Part { bone = sp.b, kind = sp.kind, region = sp.region, t = t, target = Bone(ta, sp.b),
                    left = sp.b.ToString().StartsWith("Left") };
                if (!part.target) throw new System.Exception($"target rig has no {sp.b}");
                part.parent = sp.parent == HumanBodyBones.LastBone ? null : byBone[sp.parent];
                part.pinGain = PinGain[sp.kind];
                part.baseSpring = BaseSpring.TryGetValue(sp.kind, out var bs) ? bs * s * s * s * s : 0f; // ~mass*len
                part.rb = t.gameObject.AddComponent<Rigidbody>();
                part.rb.mass = totalMass * sp.mass;
                part.rb.solverIterations = 24; part.rb.solverVelocityIterations = 8;
                part.rb.maxAngularVelocity = 40f; part.rb.linearDamping = 0.02f; part.rb.angularDamping = 0.1f;
                part.rb.interpolation = RigidbodyInterpolation.None;
                part.rb.collisionDetectionMode = CollisionDetectionMode.ContinuousDynamic;
                part.rb.isKinematic = kinematic;
                t.gameObject.layer = kinematic ? Layer + 1 : Layer;

                // colliders, on child objects so they can be oriented freely
                Vector3 a = t.position, bEnd = a;
                switch (sp.kind)
                {
                    case "hips":
                    {
                        var c = Vector3.Lerp(a, (P(HumanBodyBones.LeftUpperLeg) + P(HumanBodyBones.RightUpperLeg)) * 0.5f, 0.5f);
                        Capsule(part, c - right * hipW * 0.5f, c + right * hipW * 0.5f, 0.10f * s, mat);
                        break;
                    }
                    case "spine":
                    {
                        var c = Vector3.Lerp(a, P(HumanBodyBones.UpperChest), 0.5f);
                        Capsule(part, c - right * shoulderW * 0.33f, c + right * shoulderW * 0.33f, 0.095f * s, mat);
                        break;
                    }
                    case "chest":
                    {
                        var neck = Bone(va, HumanBodyBones.Neck) ? P(HumanBodyBones.Neck) : a + up * 0.15f * s;
                        var c = Vector3.Lerp(a, neck, 0.35f) + fwd * 0.01f * s;
                        Capsule(part, c - right * shoulderW * 0.38f, c + right * shoulderW * 0.38f, 0.11f * s, mat);
                        break;
                    }
                    case "head":
                        Sphere(part, a + up * 0.09f * s + fwd * 0.02f * s, 0.105f * s, mat);
                        break;
                    case "upperArm": bEnd = P(sp.b == HumanBodyBones.LeftUpperArm ? HumanBodyBones.LeftLowerArm : HumanBodyBones.RightLowerArm); Capsule(part, a, bEnd, 0.045f * s, mat); break;
                    case "lowerArm":
                    {
                        var hand = P(part.left ? HumanBodyBones.LeftHand : HumanBodyBones.RightHand);
                        bEnd = hand;
                        Capsule(part, a, hand + (hand - a).normalized * 0.09f * s, 0.04f * s, mat);
                        break;
                    }
                    case "upperLeg": bEnd = P(part.left ? HumanBodyBones.LeftLowerLeg : HumanBodyBones.RightLowerLeg); Capsule(part, a, bEnd, 0.075f * s, mat); break;
                    case "lowerLeg": bEnd = P(part.left ? HumanBodyBones.LeftFoot : HumanBodyBones.RightFoot); Capsule(part, a, bEnd, 0.055f * s, mat); break;
                    case "foot":
                    {
                        var toe = Bone(va, part.left ? HumanBodyBones.LeftToes : HumanBodyBones.RightToes);
                        Vector3 tip = toe ? toe.position + fwd * 0.05f * s : a + fwd * 0.17f * s;
                        bEnd = tip;
                        Vector3 heel = a - fwd * 0.06f * s;
                        float h = Mathf.Max(0.04f * s, a.y - groundY + 0.025f * s);
                        var mid = new Vector3((heel.x + tip.x) * 0.5f, groundY + h * 0.5f, (heel.z + tip.z) * 0.5f);
                        float len = Vector3.Dot(tip - heel, fwd);
                        Box(part, mid, Quaternion.LookRotation(fwd, up), new Vector3(0.095f * s, h, len), mat);
                        break;
                    }
                }
                if (sp.kind == "spine") bEnd = P(HumanBodyBones.UpperChest);
                if (sp.kind == "chest") bEnd = Bone(va, HumanBodyBones.Neck) ? P(HumanBodyBones.Neck) : a + up;
                if (sp.kind == "head") bEnd = a + up;
                if (sp.kind == "hips") bEnd = P(HumanBodyBones.Spine);
                part.boneDirLocal = Quaternion.Inverse(t.rotation) * (bEnd - a).normalized;
                part.fwdLocal = Quaternion.Inverse(t.rotation) * fwd;

                if (part.parent != null)
                {
                    part.startLocal = Quaternion.Inverse(part.parent.t.rotation) * t.rotation;
                    if (!kinematic) part.joint = MakeJoint(part, right, fwd, up, bEnd);
                }
                parts.Add(part);
                byBone[sp.b] = part;
                byBody[part.rb.GetInstanceID()] = part;
            }
            // self collisions: only left vs right leg and arm vs arm stay on (the rest overlap in normal poses)
            for (int i = 0; i < parts.Count; i++)
                for (int k = i + 1; k < parts.Count; k++)
                {
                    var A = parts[i]; var B = parts[k];
                    bool keep = (A.region == "legs" && B.region == "legs" && A.left != B.left)
                                || (A.region == "arms" && B.region == "arms" && A.left != B.left);
                    if (keep) continue;
                    foreach (var ca in A.cols) foreach (var cb in B.cols) Physics.IgnoreCollision(ca, cb, true);
                }
            foreach (var x in parts) { x.prevTargetPos = x.target.position; x.prevTargetRot = x.target.rotation; }
            foreach (var smr in go.GetComponentsInChildren<SkinnedMeshRenderer>())
            {
                smr.updateWhenOffscreen = true;
                smr.forceMatrixRecalculationPerRender = true;
            }
        }

        void Capsule(Part part, Vector3 a, Vector3 b, float r, PhysicsMaterial m)
        {
            var o = new GameObject("col_" + part.kind); o.layer = part.t.gameObject.layer;
            o.transform.SetParent(part.t, false);
            o.transform.position = (a + b) * 0.5f;
            o.transform.rotation = Quaternion.FromToRotation(Vector3.up, (b - a).normalized);
            var c = o.AddComponent<CapsuleCollider>();
            float ls = o.transform.lossyScale.x;
            c.direction = 1; c.radius = r / ls; c.height = (Vector3.Distance(a, b) + 2 * r) / ls; c.sharedMaterial = m;
            c.providesContacts = true;
            part.cols.Add(c);
        }

        void Sphere(Part part, Vector3 c0, float r, PhysicsMaterial m)
        {
            var o = new GameObject("col_" + part.kind); o.layer = part.t.gameObject.layer;
            o.transform.SetParent(part.t, false); o.transform.position = c0;
            var c = o.AddComponent<SphereCollider>(); c.radius = r / o.transform.lossyScale.x; c.sharedMaterial = m;
            c.providesContacts = true;
            part.cols.Add(c);
        }

        void Box(Part part, Vector3 c0, Quaternion rot, Vector3 size, PhysicsMaterial m)
        {
            var o = new GameObject("col_" + part.kind); o.layer = part.t.gameObject.layer;
            o.transform.SetParent(part.t, false); o.transform.SetPositionAndRotation(c0, rot);
            var c = o.AddComponent<BoxCollider>(); c.size = size / o.transform.lossyScale.x; c.sharedMaterial = m;
            c.providesContacts = true;
            part.cols.Add(c);
        }

        // anatomical joint ranges: (flex min, flex max) about the flexion axis, then swing/twist limits
        static readonly Dictionary<string, (float lo, float hi, float y, float z)> Limits = new Dictionary<string, (float, float, float, float)>
        {
            {"spine", (-25, 45, 25, 30)}, {"chest", (-20, 35, 25, 30)}, {"head", (-50, 65, 40, 70)},
            {"upperLeg", (-30, 125, 55, 45)}, {"lowerLeg", (-4, 150, 4, 12)}, {"foot", (-45, 30, 20, 25)},
            {"lowerArm", (-4, 145, 10, 80)},
        };

        ConfigurableJoint MakeJoint(Part part, Vector3 right, Vector3 fwd, Vector3 up, Vector3 bEnd)
        {
            var t = part.t;
            // flexion axis: character right for spine/legs/head, vertical for the elbow (arms are out in T-pose)
            Vector3 axisW = part.kind == "lowerArm" ? up : right;
            Vector3 secW = fwd;
            Vector3 flexDir = part.kind switch
            {
                "lowerLeg" => -fwd, "foot" => up, _ => fwd,
            };
            var j = t.gameObject.AddComponent<ConfigurableJoint>();
            j.axis = Quaternion.Inverse(t.rotation) * axisW;
            j.secondaryAxis = Quaternion.Inverse(t.rotation) * secW;
            j.connectedBody = part.parent.rb;
            j.autoConfigureConnectedAnchor = true;
            j.anchor = Vector3.zero;
            j.xMotion = j.yMotion = j.zMotion = ConfigurableJointMotion.Locked;
            if (Limits.TryGetValue(part.kind, out var L))
            {
                var v = (bEnd - t.position).normalized;
                float sgn = Vector3.Dot(Quaternion.AngleAxis(10f, axisW) * v - v, flexDir) > 0 ? 1f : -1f;
                float lo = sgn > 0 ? L.lo : -L.hi, hi = sgn > 0 ? L.hi : -L.lo;   // in AngleAxis(+a, axis) terms
                if (JointSign < 0) { var tmp = lo; lo = -hi; hi = -tmp; }
                j.angularXMotion = j.angularYMotion = j.angularZMotion = ConfigurableJointMotion.Limited;
                j.lowAngularXLimit = new SoftJointLimit { limit = Mathf.Clamp(lo, -177, 177) };
                j.highAngularXLimit = new SoftJointLimit { limit = Mathf.Clamp(hi, -177, 177) };
                j.angularYLimit = new SoftJointLimit { limit = L.y };
                j.angularZLimit = new SoftJointLimit { limit = L.z };
            }
            else j.angularXMotion = j.angularYMotion = j.angularZMotion = ConfigurableJointMotion.Free;
            j.rotationDriveMode = RotationDriveMode.Slerp;
            j.projectionMode = JointProjectionMode.PositionAndRotation;
            j.projectionDistance = 0.02f; j.projectionAngle = 4f;
            j.enablePreprocessing = false;
            j.enableCollision = false;
            var r = j.axis; var f = Vector3.Cross(j.axis, j.secondaryAxis).normalized; var u = Vector3.Cross(f, r).normalized;
            part.w2j = Quaternion.LookRotation(f, u);
            part.j2w = Quaternion.Inverse(part.w2j);
            return j;
        }

        // ------------------------------------------------------------------ runtime
        /// Direction the chest faces (up when lying on the back).
        public Vector3 ChestForward() { var c = Get(HumanBodyBones.UpperChest); return c.t.rotation * c.fwdLocal; }

        public Part Get(HumanBodyBones b) => byBone.TryGetValue(b, out var x) ? x : null;
        public bool TryPart(int bodyInstanceId, out Part part) => byBody.TryGetValue(bodyInstanceId, out part);

        public Vector3 COM()
        {
            Vector3 c = Vector3.zero; float m = 0;
            foreach (var x in parts) { c += x.rb.worldCenterOfMass * x.rb.mass; m += x.rb.mass; }
            return c / m;
        }

        public Vector3 COMVelocity()
        {
            Vector3 v = Vector3.zero; float m = 0;
            foreach (var x in parts) { v += x.rb.linearVelocity * x.rb.mass; m += x.rb.mass; }
            return v / m;
        }

        float RegionGain(string region) => region switch
        {
            "legs" => p.legs, "spine" => p.spine, "arms" => p.arms, "neck" => p.neck, _ => 1f,
        };

        void Log(string s) { log.Add($"{simTime:F2} {id}: {s}"); }

        void SetState(RagdollState s, string why)
        {
            if (state == s) return;
            state = s; stateTime = 0; Log($"{s} ({why})");
        }

        /// Scripted or collision hit. impulse in N*s (world), at body part `part`. apply: also push the body.
        public void Hit(Part part, Vector3 impulse, Vector3 point, bool apply, string what)
        {
            if (kinematic) { if (apply) { } return; }
            if (apply)
            {
                part.rb.AddForceAtPosition(impulse, point, ForceMode.Impulse);
            }
            float dv = impulse.magnitude / totalMass;
            if (dv < 0.03f) return;
            // sustained contact (leaning on a crate, crowd pressure) reports every step: only fresh or big impacts count
            if (simTime - part.lastHit < 0.25f && dv < 0.3f) { part.lastHit = simTime; return; }
            part.lastHit = simTime;
            lastHitTime = simTime;
            // tripping: a leg caught on an obstacle while walking pitches the body over it (fighters catch themselves)
            if (what == "obstacle" && part.region == "legs" && state == RagdollState.Puppet)
            {
                var tv = hips.targetVel; tv.y = 0;
                if (tv.magnitude > 0.5f && p.knockdown < 2f)
                {
                    foreach (var x in parts) if (x.region == "legs") x.local = Mathf.Min(x.local, 1f - p.hitLimp);
                    Fall(tv, $"tripped over an obstacle ({part.bone})");
                    return;
                }
            }
            // local limpness: the struck part and its neighbours (graph distance) lose tone
            foreach (var x in parts)
            {
                int d = Dist(x, part);
                float fall = d == 0 ? 1f : d == 1 ? 0.6f : d == 2 ? 0.25f : 0f;
                x.local = Mathf.Min(x.local, 1f - p.hitLimp * fall * Mathf.Clamp01(dv / Mathf.Max(0.2f, p.knockdown * 0.5f)));
            }
            recentDv = recentDv * Mathf.Exp(-(simTime - recentT) / 0.3f) + dv; recentT = simTime;
            pin = Mathf.Max(0f, pin - dv * p.hitBalanceLoss);
            if (dv >= 0.1f) Log($"hit {what} on {part.bone} dv={dv:F2} -> pin {pin:F2}");
            if (state == RagdollState.Puppet && recentDv >= p.knockdown)
                Fall(new Vector3(impulse.x, 0, impulse.z).normalized, $"knocked down by {what} (dv {recentDv:F2} >= {p.knockdown:F2})");
            else if (state == RagdollState.GettingUp && dv >= p.knockdown * 0.6f)
                Fall(new Vector3(impulse.x, 0, impulse.z).normalized, $"knocked over while getting up by {what}");
        }

        static int Dist(Part a, Part b)
        {
            // distance in the body tree (small tree, brute force through the ancestor chains)
            var anc = new List<Part>();
            for (var x = a; x != null; x = x.parent) anc.Add(x);
            int db = 0;
            for (var y = b; y != null; y = y.parent, db++)
            {
                int i = anc.IndexOf(y);
                if (i >= 0) return i + db;
            }
            return 99;
        }

        public void Fall(Vector3 dir, string why)
        {
            if (state == RagdollState.Falling || state == RagdollState.Lying) return;
            fallDir = dir.sqrMagnitude > 1e-4f ? dir.normalized : go.transform.forward;
            track.frozen = true;
            stillTime = 0;
            SetState(RagdollState.Falling, why);
        }

        public void PreStep(float dt, float t)
        {
            simTime = t;
            stateTime += dt;
            // advance the target animation (root motion moves the hidden target)
            track.Step(dt);
            foreach (var x in parts)
            {
                var tp = x.target.position;
                x.targetVel = (tp - x.prevTargetPos) / dt;
                x.prevTargetPos = tp; x.prevTargetRot = x.target.rotation;
            }
            if (kinematic)
            {
                foreach (var x in parts) { x.rb.MovePosition(x.target.position); x.rb.MoveRotation(x.target.rotation); }
                return;
            }
            UpdateState(dt);
            Drive(dt);
        }

        void UpdateState(float dt)
        {
            bool reacting = simTime - lastHitTime > p.reactionTime;
            foreach (var x in parts) if (reacting) x.local = Mathf.MoveTowards(x.local, 1f, p.recovery * 0.5f * dt);
            Vector3 hipErr = hips.rb.position - hips.target.position;
            float horiz = new Vector2(hipErr.x, hipErr.z).magnitude;
            switch (state)
            {
                case RagdollState.Puppet:
                {
                    if (reacting) pin = Mathf.MoveTowards(pin, 1f, p.recovery * 0.35f * dt);
                    tone = Mathf.MoveTowards(tone, 1f, 4f * dt);
                    // stumble: the animation follows a displaced body instead of pulling it back
                    if (horiz > 0.05f && p.stepFollow > 0)
                    {
                        var d = new Vector3(hipErr.x, 0, hipErr.z);
                        float step = Mathf.Min(horiz - 0.04f, p.stepFollow * dt);
                        track.go.transform.position += d.normalized * step;
                    }
                    var chestP = Get(HumanBodyBones.UpperChest);
                    float tilt = Vector3.Angle(chestP.t.rotation * chestP.boneDirLocal, chestP.target.rotation * chestP.boneDirLocal);
                    if (horiz > p.balanceRadius) Fall(new Vector3(hipErr.x, 0, hipErr.z), $"pushed off balance ({horiz:F2} m)");
                    else if (unsupported > 0.3f && hips.rb.position.y < hips.target.position.y - 0.08f * scale) Fall(COMVelocity(), $"no ground under the feet (feet y {Get(HumanBodyBones.LeftFoot).rb.position.y:F2}/{Get(HumanBodyBones.RightFoot).rb.position.y:F2}, targets {Get(HumanBodyBones.LeftFoot).target.position.y:F2}/{Get(HumanBodyBones.RightFoot).target.position.y:F2}, hips {hips.rb.position.y:F2} vs {hips.target.position.y:F2})");
                    else if (tilt > 50f) Fall(new Vector3(hipErr.x, 0, hipErr.z), $"trunk tipped over ({tilt:F0} deg)");
                    else if (hips.rb.position.y < hips.target.position.y - 0.35f * scale) Fall(COMVelocity(), "legs gave way");
                    break;
                }
                case RagdollState.Falling:
                {
                    pin = Mathf.MoveTowards(pin, 0f, 8f * dt);
                    tone = Mathf.MoveTowards(tone, p.fallTone, 6f * dt);
                    float spd = COMVelocity().magnitude;
                    stillTime = spd < 0.25f ? stillTime + dt : 0f;
                    if (stateTime > 0.9f && stillTime > 0.5f) SetState(RagdollState.Lying, "came to rest");
                    break;
                }
                case RagdollState.Lying:
                {
                    pin = 0; tone = Mathf.MoveTowards(tone, p.fallTone, 2f * dt);
                    if (p.getUpDelay >= 0 && stateTime > p.getUpDelay && chooseGetUp != null) BeginGetUp();
                    break;
                }
                case RagdollState.GettingUp:
                {
                    float gt = stateTime;
                    tone = Mathf.Lerp(p.fallTone, 1f, Mathf.SmoothStep(0, 1, gt / 0.5f));
                    pin = Mathf.Lerp(0f, 1f, Mathf.SmoothStep(0, 1, (gt - 0.15f) / 1.0f));
                    if (track.clip && track.time >= track.length - 0.35f)
                    {
                        if (afterGetUp) track.Play(afterGetUp, 0, 1, 0.3f, afterGetUpLoop); else track.loop = false;
                        SetState(RagdollState.Puppet, "stood up");
                    }
                    break;
                }
            }
        }

        void BeginGetUp()
        {
            var (clip, start) = chooseGetUp(this);
            if (!clip) return;
            // place the target so its hips (at the clip start) sit on the body's hips, facing the same way
            var head = Get(HumanBodyBones.Head);
            Vector3 hipsP = hips.rb.position;
            Vector3 bodyAxis = head.rb.position - hipsP; bodyAxis.y = 0;
            track.Play(clip, start, p.getUpSpeed, 0f, false);
            track.go.transform.rotation = Quaternion.identity;
            track.Refresh();
            var tAxis = Get(HumanBodyBones.Head).target.position - hips.target.position; tAxis.y = 0;
            float yaw = Vector3.SignedAngle(tAxis, bodyAxis, Vector3.up);
            float gy = groundAt != null ? groundAt(hipsP) : 0f;
            track.PlaceBone(HumanBodyBones.Hips, hipsP, yaw, gy);
            foreach (var x in parts) { x.prevTargetPos = x.target.position; x.local = 1f; }
            getUpStart = simTime;
            SetState(RagdollState.GettingUp, $"{clip.name} from {start:F2}s, yaw {yaw:F0}");
        }

        void Drive(float dt)
        {
            var chest = Get(HumanBodyBones.UpperChest);
            bool brace = state == RagdollState.Falling && stateTime > p.reactionTime && p.brace > 0.01f;
            float pinW = pin * p.balance * anticipationBoost;
            bool lyingOrFalling = state == RagdollState.Falling || state == RagdollState.Lying;
            float g = Physics.gravity.magnitude;
            foreach (var x in parts)
            {
                // ---- muscles ----
                if (x.joint)
                {
                    Quaternion targetLocal = Quaternion.Inverse(x.parent.target.rotation) * x.target.rotation;
                    float m = tone * x.local * p.strength * RegionGain(x.region) * anticipationBoost;
                    if (brace && x.region == "arms")
                    {
                        // protective reflex: reach toward the fall direction, straight-ish arms
                        if (x.kind == "upperArm")
                        {
                            var side = chest.t.rotation * Vector3.right; // not anatomical, just "away from body"
                            Vector3 sideOut = (x.left ? -1f : 1f) * Vector3.ProjectOnPlane(go.transform.right, Vector3.up).normalized;
                            sideOut = Vector3.Dot(sideOut, x.t.position - chest.t.position) < 0 ? -sideOut : sideOut;
                            var want = (fallDir * 0.9f + Vector3.down * 0.55f + sideOut * 0.3f).normalized;
                            var rest = x.parent.t.rotation * x.startLocal;
                            var restDir = rest * x.boneDirLocal;
                            var desired = Quaternion.FromToRotation(restDir, want) * rest;
                            targetLocal = Quaternion.Inverse(x.parent.t.rotation) * desired;
                        }
                        else targetLocal = x.startLocal; // straight elbow
                        m = Mathf.Max(m, p.brace * p.arms * 0.9f);
                    }
                    else if (brace && x.kind == "head")
                        m = Mathf.Max(m, p.brace * p.neck * 0.6f);
                    float k = x.baseSpring * Mathf.Max(0.01f, m);
                    var jd = new JointDrive
                    {
                        positionSpring = k,
                        positionDamper = k * 0.06f * p.damping + (lyingOrFalling ? 2f * scale : 0f),
                        maximumForce = k * 1.6f,
                    };
                    x.joint.slerpDrive = jd;
                    x.joint.targetRotation = x.j2w * (Quaternion.Inverse(targetLocal) * x.startLocal) * x.w2j;
                }
                // ---- balance assist (pins) ----
                if (pinW > 1e-3f)
                {
                    float w = pinW * x.pinGain;
                    if (x.local < 1f) w *= x.local; // a struck limb isn't held either
                    var a = PinKp * (x.target.position - x.rb.position) + PinKd * (x.targetVel - x.rb.linearVelocity);
                    if (unsupported > 0.08f && a.y > 0) a.y *= 0.25f; // no hovering without ground under the feet
                    a = Vector3.ClampMagnitude(a * w, PinMaxAcc * w);
                    x.rb.AddForce(a, ForceMode.Acceleration);
                }
            }
            if (pinW > 1e-3f)
            {
                // keep hips (and chest) oriented like the animation
                foreach (var x in new[] { hips, chest })
                {
                    var err = x.target.rotation * Quaternion.Inverse(x.rb.rotation);
                    err.ToAngleAxis(out float ang, out Vector3 axis);
                    if (ang > 180) ang -= 360;
                    if (float.IsNaN(axis.x) || Mathf.Abs(ang) < 1e-3f) axis = Vector3.zero;
                    var alpha = HipKpA * (ang * Mathf.Deg2Rad) * axis - HipKdA * x.rb.angularVelocity;
                    alpha = Vector3.ClampMagnitude(alpha * pinW * (x == hips ? 1f : 0.5f), 250f);
                    x.rb.AddTorque(alpha, ForceMode.Acceleration);
                }
            }
            if (p.sway > 0 && state == RagdollState.Puppet)
            {
                float n1 = Mathf.PerlinNoise(simTime * 0.6f, id.GetHashCode() % 100) * 2 - 1;
                float n2 = Mathf.PerlinNoise(simTime * 0.6f + 37, id.GetHashCode() % 100) * 2 - 1;
                chest.rb.AddForce(new Vector3(n1, 0, n2) * p.sway * totalMass * g);
            }
        }

        public void PostStep(float dt)
        {
            if (kinematic) return;
            // ground contact of the feet (for "no ground under the feet")
            foreach (var x in parts)
            {
                if (x.kind != "foot") continue;
                var c = (BoxCollider)x.cols[0];
                var tr = c.transform;
                var half = Vector3.Scale(c.size * 0.5f, tr.lossyScale);
                x.grounded = Physics.CheckBox(tr.TransformPoint(c.center) - Vector3.up * 0.07f * scale, half, tr.rotation,
                    ~((1 << Layer) | (1 << (Layer + 1))), QueryTriggerInteraction.Ignore);
            }
            bool feet = false;
            foreach (var x in parts) if (x.kind == "foot" && x.grounded) feet = true;
            unsupported = feet || state == RagdollState.GettingUp ? 0f : unsupported + dt;
            // metrics
            bool undisturbed = state == RagdollState.Puppet && simTime - lastHitTime > 2.0f && stateTime > 1.5f;
            float pe = 0, ae = 0; int n = 0;
            foreach (var x in parts)
            {
                var v = x.rb.linearVelocity; var w = x.rb.angularVelocity;
                if (float.IsNaN(v.x) || float.IsNaN(x.rb.position.x)) nanCount++;
                maxLinVel = Mathf.Max(maxLinVel, v.magnitude); maxAngVel = Mathf.Max(maxAngVel, w.magnitude);
                if (undisturbed)
                {
                    pe += Vector3.Distance(x.rb.position, x.target.position);
                    if (x.parent != null)
                    {
                        var lp = Quaternion.Inverse(x.parent.t.rotation) * x.t.rotation;
                        var lt = Quaternion.Inverse(x.parent.target.rotation) * x.target.rotation;
                        ae += Quaternion.Angle(lp, lt); n++;
                    }
                }
            }
            if (undisturbed)
            {
                float mpe = pe / parts.Count;
                trackPosErrSum += mpe; trackAngErrSum += ae / Mathf.Max(1, n); trackSamples++;
                trackPosErrMax = Mathf.Max(trackPosErrMax, mpe);
            }
            if (state == RagdollState.Lying && stateTime > 0.3f)
            {
                lyingSpeedSqSum += hips.rb.linearVelocity.sqrMagnitude; lyingSamples++;
            }
        }

        public string MetricsJson()
        {
            var inv = System.Globalization.CultureInfo.InvariantCulture;
            string F(double v) => v.ToString("0.####", inv);
            return "{" + $"\"id\":\"{id}\",\"personality\":\"{p.name}\",\"kinematic\":{(kinematic ? "true" : "false")}," +
                   $"\"track_pos_err_cm\":{F(trackSamples > 0 ? 100 * trackPosErrSum / trackSamples : -1)}," +
                   $"\"track_pos_err_max_cm\":{F(100 * trackPosErrMax)}," +
                   $"\"track_joint_err_deg\":{F(trackSamples > 0 ? trackAngErrSum / trackSamples : -1)}," +
                   $"\"track_samples\":{trackSamples},\"max_ang_vel\":{F(maxAngVel)},\"max_lin_vel\":{F(maxLinVel)}," +
                   $"\"nan\":{nanCount},\"lying_hip_rms_speed\":{F(lyingSamples > 0 ? System.Math.Sqrt(lyingSpeedSqSum / lyingSamples) : -1)}," +
                   $"\"final_state\":\"{state}\"" + "}";
        }
    }
}
