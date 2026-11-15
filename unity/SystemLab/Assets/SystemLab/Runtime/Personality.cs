// Physical "personality" of an active ragdoll: how strong its muscles are, how much balance assist it gets, how fast
// it reacts, whether it braces when it falls and how it gets up. Text maps to these numbers (demo/ragdoll/personality.py
// or Claude filling the JSON directly); the same fields are the `personality` argument of simulate_reaction.
using UnityEngine;

namespace SystemLab
{
    [System.Serializable]
    public class Personality
    {
        public string name = "average";
        [Tooltip("Global muscle strength multiplier (PD spring on every joint).")]
        public float strength = 1f;
        [Tooltip("Per-region strength multipliers.")]
        public float legs = 1f, spine = 1f, arms = 1f, neck = 1f;
        [Tooltip("Damping multiplier (higher = heavier, slower, less springy).")]
        public float damping = 1f;
        [Tooltip("Balance assist when nothing is happening (0 = pure physics, 1 = fully pinned to the animation).")]
        public float balance = 1f;
        [Tooltip("Body-velocity change (m/s) from a hit that already makes the character fall.")]
        public float knockdown = 0.8f;
        [Tooltip("How far (m) the hips may be pushed off the animation before balance is lost.")]
        public float balanceRadius = 0.35f;
        [Tooltip("Balance assist lost per m/s of hit.")]
        public float hitBalanceLoss = 0.9f;
        [Tooltip("How limp the hit body part and its neighbours go (0 = not at all, 1 = fully).")]
        public float hitLimp = 0.7f;
        [Tooltip("Seconds before reflexes (bracing, recovery) start.")]
        public float reactionTime = 0.12f;
        [Tooltip("Muscle and balance recovery per second after a hit.")]
        public float recovery = 2.5f;
        [Tooltip("Arm bracing toward the fall direction (0 = flops, 1 = catches themselves).")]
        public float brace = 0.8f;
        [Tooltip("Stiffens just before a visible impact (trained people tense up).")]
        public float anticipation = 0f;
        [Tooltip("Muscle strength while falling and lying.")]
        public float fallTone = 0.25f;
        [Tooltip("How fast the animation follows a displaced body, m/s (stumble steps instead of rubber-banding back).")]
        public float stepFollow = 1.2f;
        [Tooltip("Random sway force (drunk), as a fraction of body weight.")]
        public float sway = 0f;
        [Tooltip("Seconds lying still before getting up (<0 = stays down).")]
        public float getUpDelay = 1.0f;
        [Tooltip("Playback speed of the get-up clip.")]
        public float getUpSpeed = 1f;

        public Personality Clone() => (Personality)MemberwiseClone();

        public static Personality Preset(string key)
        {
            switch ((key ?? "average").ToLowerInvariant())
            {
                case "frail_elder":
                    return new Personality
                    {
                        name = "frail_elder", strength = 0.55f, legs = 0.8f, arms = 0.6f, neck = 0.7f, damping = 1.3f,
                        balance = 0.75f, knockdown = 0.55f, balanceRadius = 0.2f, hitBalanceLoss = 1.1f, hitLimp = 0.85f,
                        reactionTime = 0.3f, recovery = 1.0f, brace = 0.35f, fallTone = 0.18f, stepFollow = 0.5f,
                        getUpDelay = 2.2f, getUpSpeed = 0.7f
                    };
                case "trained_fighter":
                    return new Personality
                    {
                        name = "trained_fighter", strength = 1.35f, legs = 1.3f, spine = 1.2f, arms = 1.2f, neck = 1.3f,
                        damping = 1.0f, balance = 1f, knockdown = 2.4f, balanceRadius = 0.55f, hitBalanceLoss = 0.3f,
                        hitLimp = 0.4f, reactionTime = 0.06f, recovery = 5f, brace = 1f, anticipation = 0.6f,
                        fallTone = 0.45f, stepFollow = 2.2f, getUpDelay = 0.4f, getUpSpeed = 1.25f
                    };
                case "drunk":
                    return new Personality
                    {
                        name = "drunk", strength = 0.7f, legs = 0.75f, spine = 0.6f, arms = 0.5f, neck = 0.4f,
                        damping = 0.7f, balance = 0.55f, knockdown = 0.45f, balanceRadius = 0.3f, hitBalanceLoss = 1.2f,
                        hitLimp = 0.95f, reactionTime = 0.45f, recovery = 0.8f, brace = 0.05f, fallTone = 0.08f,
                        stepFollow = 0.9f, sway = 0.05f, getUpDelay = 2.8f, getUpSpeed = 0.8f
                    };
                case "ragdoll":  // no muscles at all once hit: the classic "dead" ragdoll, for comparison
                    return new Personality
                    {
                        name = "ragdoll", strength = 1f, balance = 1f, knockdown = 0.01f, hitLimp = 1f, reactionTime = 9f,
                        recovery = 0f, brace = 0f, fallTone = 0.02f, getUpDelay = -1f
                    };
                default:
                    return new Personality();
            }
        }

        public static Personality FromJson(string json)
        {
            var p = new Personality();
            JsonUtility.FromJsonOverwrite(json, p);
            return p;
        }
    }
}
