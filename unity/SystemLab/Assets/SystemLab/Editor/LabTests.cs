// One-off physics checks for the active ragdoll (run headless):
//   Unity.exe -batchmode -projectPath unity/SystemLab -executeMethod SystemLab.LabTests.Run -logFile -
// JointSign: which way ConfigurableJoint X limits count relative to Quaternion.AngleAxis (sets ActiveRagdoll.JointSign).
// Contacts: Physics.ContactEvent fires for Physics.Simulate in edit mode (hit detection relies on it).
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace SystemLab
{
    public static class LabTests
    {
        public static void Run()
        {
            int code = 0;
            try
            {
                LabSetup.Ensure();
                JointSign();
                Contacts();
            }
            catch (System.Exception e) { Debug.LogError("LAB_ERROR " + e); code = 1; }
            EditorApplication.Exit(code);
        }

        static void JointSign()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Physics.gravity = Vector3.zero;
            var parent = GameObject.CreatePrimitive(PrimitiveType.Cube);
            var prb = parent.AddComponent<Rigidbody>(); prb.isKinematic = true;
            var child = GameObject.CreatePrimitive(PrimitiveType.Cube);
            child.transform.position = new Vector3(0, -1.2f, 0);
            Physics.IgnoreCollision(parent.GetComponent<Collider>(), child.GetComponent<Collider>());
            var crb = child.AddComponent<Rigidbody>();
            var j = child.AddComponent<ConfigurableJoint>();
            j.axis = Vector3.right; j.secondaryAxis = Vector3.up; j.connectedBody = prb;
            j.anchor = new Vector3(0, 0.6f, 0);
            j.xMotion = j.yMotion = j.zMotion = ConfigurableJointMotion.Locked;
            j.angularXMotion = ConfigurableJointMotion.Limited;
            j.angularYMotion = j.angularZMotion = ConfigurableJointMotion.Locked;
            j.lowAngularXLimit = new SoftJointLimit { limit = 0 };
            j.highAngularXLimit = new SoftJointLimit { limit = 60 };
            Physics.Simulate(0.01f);
            // rotate the child +30 deg about +X around the anchor
            var pivot = child.transform.TransformPoint(j.anchor);
            var q = Quaternion.AngleAxis(30, Vector3.right);
            crb.position = pivot + q * (crb.position - pivot); crb.rotation = q * crb.rotation;
            child.transform.SetPositionAndRotation(crb.position, crb.rotation);
            for (int i = 0; i < 60; i++) Physics.Simulate(0.01f);
            float ang = Vector3.SignedAngle(Vector3.down, (crb.position - pivot).normalized, Vector3.right);
            Debug.Log($"LAB_TEST joint_sign: after +30 about X the child sits at {ang:F1} deg -> JointSign = {(ang > 15 ? "+1" : "-1")}");

            // targetRotation check with the standard formula: drive to local +40 deg about X
            j.angularXMotion = ConfigurableJointMotion.Free;
            j.rotationDriveMode = RotationDriveMode.Slerp;
            j.slerpDrive = new JointDrive { positionSpring = 500, positionDamper = 20, maximumForce = 1e9f };
            var start = Quaternion.identity; var target = Quaternion.AngleAxis(40, Vector3.right);
            j.targetRotation = Quaternion.Inverse(target) * start;
            for (int i = 0; i < 300; i++) Physics.Simulate(0.01f);
            float ang2 = Vector3.SignedAngle(Vector3.down, (crb.position - pivot).normalized, Vector3.right);
            Debug.Log($"LAB_TEST target_rotation: asked local +40 deg about X, got {ang2:F1} deg");
            Physics.gravity = new Vector3(0, -9.81f, 0);
        }

        static int events;
        static void Contacts()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
            floor.transform.localScale = new Vector3(10, 1, 10); floor.transform.position = new Vector3(0, -0.5f, 0);
            var ball = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            ball.transform.position = new Vector3(0, 2, 0);
            ball.AddComponent<Rigidbody>();
            ball.GetComponent<Collider>().providesContacts = true;
            events = 0;
            Physics.ContactEvent += On;
            for (int i = 0; i < 200; i++) Physics.Simulate(0.01f);
            Physics.ContactEvent -= On;
            Debug.Log($"LAB_TEST contact_events: {events} pair reports in edit mode (needs > 0)");
        }

        static void On(PhysicsScene s, Unity.Collections.NativeArray<ContactPairHeader>.ReadOnly h) { events += h.Length; }
    }
}
