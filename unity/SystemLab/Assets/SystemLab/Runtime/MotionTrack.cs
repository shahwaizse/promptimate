// The kinematic "target" character: an invisible copy of the rig that plays Promptimate clips (Humanoid, root motion)
// on a manually stepped PlayableGraph. The active ragdoll's muscles track its pose.
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

namespace SystemLab
{
    public class MotionTrack
    {
        public readonly GameObject go;
        public readonly Animator anim;
        PlayableGraph graph;
        AnimationMixerPlayable mixer;
        readonly AnimationClipPlayable[] slot = new AnimationClipPlayable[2];
        int cur = -1;
        float fadeT, fadeLen;
        public AnimationClip clip { get; private set; }
        public float speed { get; private set; } = 1f;
        public bool frozen;
        public bool loop;
        /// Foot IK needs the IK goal curves Promptimate's importer writes; clips baked from physics have none.
        public bool footIK = true;

        public MotionTrack(GameObject target)
        {
            go = target;
            anim = target.GetComponent<Animator>();
            anim.applyRootMotion = true;
            anim.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            graph = PlayableGraph.Create("target_" + target.name);
            graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
            mixer = AnimationMixerPlayable.Create(graph, 2);
            AnimationPlayableOutput.Create(graph, "out", anim).SetSourcePlayable(mixer);
            graph.Play();
        }

        public float time => cur >= 0 ? (float)slot[cur].GetTime() : 0f;
        public float length => clip ? clip.length : 0f;
        public bool finished => clip && !loop && time >= clip.length - 1e-3f;

        /// Starts `c` at clip time t0. fade > 0 crossfades from the current clip (root motion keeps flowing).
        public void Play(AnimationClip c, float t0 = 0f, float spd = 1f, float fade = 0f, bool loopClip = false)
        {
            int next = cur < 0 ? 0 : 1 - cur;
            if (slot[next].IsValid()) { graph.Disconnect(mixer, next); slot[next].Destroy(); }
            var p = AnimationClipPlayable.Create(graph, c);
            p.SetApplyFootIK(footIK);
            p.SetSpeed(spd);
            p.SetTime(t0);
            p.SetTime(t0); // twice: also resets the previous time, so the jump adds no root motion
            graph.Connect(p, 0, mixer, next);
            slot[next] = p;
            if (cur < 0 || fade <= 0f)
            {
                if (cur >= 0 && slot[cur].IsValid()) { graph.Disconnect(mixer, cur); slot[cur].Destroy(); }
                mixer.SetInputWeight(next, 1f);
                fadeLen = 0;
            }
            else { fadeLen = fade; fadeT = 0; mixer.SetInputWeight(next, 0f); mixer.SetInputWeight(cur, 1f); }
            cur = next;
            clip = c; speed = spd; loop = loopClip; frozen = false;
            graph.Evaluate(0f);
        }

        public void Step(float dt)
        {
            if (cur < 0 || frozen) return;
            if (fadeLen > 0)
            {
                fadeT += dt;
                float w = Mathf.Clamp01(fadeT / fadeLen);
                mixer.SetInputWeight(cur, w);
                mixer.SetInputWeight(1 - cur, 1 - w);
                if (w >= 1f)
                {
                    graph.Disconnect(mixer, 1 - cur); slot[1 - cur].Destroy(); fadeLen = 0;
                }
            }
            if (loop && clip && slot[cur].GetTime() + dt * speed > clip.length)
            {
                // wrap without a root-motion jump: Unity carries root motion across the wrap of a looping clip only
                // when the clip is marked looping, so restart by hand
                float t = (float)slot[cur].GetTime() + dt * speed - clip.length;
                graph.Evaluate((float)(clip.length - slot[cur].GetTime()) / speed);
                slot[cur].SetTime(0); slot[cur].SetTime(0);
                graph.Evaluate(t / speed);
                return;
            }
            if (!loop && clip && slot[cur].GetTime() >= clip.length) { graph.Evaluate(0f); return; }
            graph.Evaluate(dt);
        }

        /// Re-evaluates the current pose without advancing time (after moving the root by hand).
        public void Refresh() { if (cur >= 0) graph.Evaluate(0f); }

        /// Moves the target root so that bone `b` lands at world xz `pos` with the root rotated by `yaw` degrees.
        public void PlaceBone(HumanBodyBones b, Vector3 pos, float yaw, float groundY)
        {
            go.transform.rotation = Quaternion.Euler(0, yaw, 0);
            Refresh();
            var bt = anim.GetBoneTransform(b);
            var d = pos - bt.position;
            go.transform.position += new Vector3(d.x, 0, d.z);
            go.transform.position = new Vector3(go.transform.position.x, groundY, go.transform.position.z);
            Refresh();
        }

        public void Destroy() { if (graph.IsValid()) graph.Destroy(); }
    }
}
