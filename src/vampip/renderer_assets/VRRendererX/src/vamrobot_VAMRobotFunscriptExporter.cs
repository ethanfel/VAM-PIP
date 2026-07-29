// VAMRobotFunscriptExporter v1.0
// by vamrobot
// License: MIT

using System;
using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using SimpleJSON;
using System.Text;
using System.Net;
using System.Net.Sockets;
using System.Linq;
using System.IO;
using System.Diagnostics;
using System.IO.Ports;
using MVR.FileManagementSecure;

namespace vamrobot
{
    public class VAMRobotFunscriptExporter
    {
        public bool multiaxis = true;
        public JSONStorableStringChooser maleChooser;
        public UIDynamicPopup maleChooserPopup;
        public List<Female> females;
        public List<Male> males;
        public FunscriptAxis funscriptAxisL0 = new FunscriptAxis("stroke");
        public FunscriptAxis funscriptAxisL1 = new FunscriptAxis("sway");
        public FunscriptAxis funscriptAxisL2 = new FunscriptAxis("surge");
        public FunscriptAxis funscriptAxisL3 = new FunscriptAxis("suck");
        public FunscriptAxis funscriptAxisR0 = new FunscriptAxis("twist");
        public FunscriptAxis funscriptAxisR1 = new FunscriptAxis("roll");
        public FunscriptAxis funscriptAxisR2 = new FunscriptAxis("pitch");
        public FunscriptAxis funscriptAxisV0 = new FunscriptAxis("vib");
        public FunscriptAxis funscriptAxisV1 = new FunscriptAxis("lube");
        public FunscriptAxis funscriptAxisA0 = new FunscriptAxis("valve");
        public FunscriptAxis funscriptAxisA1 = new FunscriptAxis("suck");
        public FunscriptAxis funscriptAxisA3 = new FunscriptAxis("compression");
        public FunscriptAxis funscriptAxisA4 = new FunscriptAxis("bend");

        public void SetupFunscriptExporter(MVRScript script, string funscriptMode)
        {
            if (funscriptMode == "Multiple Axis")
            {
                multiaxis = true;
            }
            else if (funscriptMode == "Single Axis")
            {
                multiaxis = false;
            }
            else
            {
                multiaxis = true;
            }

            funscriptAxisL0.Reset();
            funscriptAxisL1.Reset();
            funscriptAxisL2.Reset();
            funscriptAxisL3.Reset();
            funscriptAxisR0.Reset();
            funscriptAxisR1.Reset();
            funscriptAxisR2.Reset();
            funscriptAxisV0.Reset();
            funscriptAxisV1.Reset();
            funscriptAxisA0.Reset();
            funscriptAxisA1.Reset();
            funscriptAxisA3.Reset();
            funscriptAxisA4.Reset();
        }

        public string RecordFunscriptFrame(MVRScript script, int frameCounter, int frameRate)
        {
            // Check if the atoms in the scene have changed and update the male and female objects and male selector drop down
            // Find all 'Person' Atoms currently in the scene
            Atom tempAtom;
            bool atomsChanged = false;

            if (females == null || males == null)
            {
                atomsChanged = true;
            }
            else if (females.Count == 0 || males.Count == 0)
            {
                atomsChanged = true;
            }
            else
            {
                int atomCount = 0;

                foreach (string atomUID in SuperController.singleton.GetAtomUIDs())
                {
                    tempAtom = SuperController.singleton.GetAtomByUid(atomUID);
                    if (tempAtom.type == "Person")
                    {
                        bool atomFound = false;
                        atomCount++;

                        // Update female(s) data
                        for (int f = 0; f < females.Count(); f++)
                        {
                            if (females[f].name == atomUID)
                            {
                                atomFound = true;
                            }
                        }

                        // Update male(s) data
                        for (int m = 0; m < males.Count(); m++)
                        {
                            if (males[m].name == atomUID)
                            {
                                atomFound = true;
                            }
                        }

                        if (!atomFound)
                        {
                            atomsChanged = true;
                        }
                    }
                }

                if (atomCount != (females.Count + males.Count))
                {
                    atomsChanged = true;
                }
            }

            if (atomsChanged)
            {
                females = null;
                males = null;
                females = new List<Female>();
                males = new List<Male>();
                foreach (string atomUID in SuperController.singleton.GetAtomUIDs())
                {
                    tempAtom = SuperController.singleton.GetAtomByUid(atomUID);
                    if (tempAtom.type == "Person")
                    {
                        string sex = "female";

                        // Check if the penis tip collider exists to determine if male or female
                        try
                        {
                            foreach (Collider c in tempAtom.gameObject.GetComponentsInChildren<Collider>())
                            {
                                // Check if the penis tip collider exists to determine if male or female
                                if (c.gameObject.name == "AutoColliderGen3bHard")
                                {
                                    sex = "male";
                                }
                            }
                        }
                        catch { sex = "female"; }

                        if (sex == "female")
                        {
                            females.Add(new Female(atomUID));
                        }
                        else
                        {
                            males.Add(new Male(atomUID));
                        }
                    }
                }

                if (maleChooserPopup != null)
                {
                    script.RemovePopup(maleChooserPopup);
                }

                string maleChooserSelection = "";

                if (maleChooser != null)
                {
                    maleChooserSelection = maleChooser.val;
                    script.DeregisterStringChooser(maleChooser);
                }

                // Setup male selector
                List<string> malesList = new List<string>();
                int maleSelection = 0;
                for (int m = 0; m < males.Count(); m++)
                {
                    malesList.Add(males[m].name);

                    if (maleChooserSelection == males[m].name)
                    {
                        maleSelection = m;
                    }
                }
                maleChooser = new JSONStorableStringChooser("Male Chooser", malesList, malesList[maleSelection], "Select Male", MaleChooserCallback);
                script.RegisterStringChooser(maleChooser);
                maleChooserPopup = script.CreatePopup(maleChooser, true);
                maleChooserPopup.labelWidth = 300f;
            }

            // Update female(s) data
            for (int f = 0; f < females.Count(); f++)
            {
                females[f].update();
            }

            // Update male(s) data
            for (int m = 0; m < males.Count(); m++)
            {
                males[m].update();
            }

            // Cycle through any male to identify the male (if more than one male is in the scene) that was selected through
            // the VAM UI selector and who's penis is the basis for driving the robot
            for (int m = 0; m < males.Count(); m++)
            {
                if (males[m].name == maleChooser.val)
                {
                    // Once the male is found, cycle through any females in the scene
                    for (int f = 0; f < females.Count(); f++)
                    {
                        // Loop through the vagina triggers and look for any collisions between them and any other colliders in the scene
                        for (int i = 0; i < females[f].vaginaTriggers.Length; i++)
                        {
                            Dictionary<Collider, bool> vaginaDictionary = females[f].vaginaRigidbodies[i].GetComponent<CollisionTriggerEventHandler>().collidingWithDictionary;

                            // Check for any collisions, zero if no collisions currently occurring
                            if (vaginaDictionary.Count > 0)
                            {
                                foreach (KeyValuePair<Collider, bool> entry in vaginaDictionary)
                                {
                                    // Loop through penis colliders
                                    for (int c = 0; c < males[m].penisNames.Length; c++)
                                    {
                                        // Check if one of the penis colliders is having a collision with the current female's vagina trigger
                                        //if (entry.Key.gameObject.name == males[m].penisNames[c])
                                        //{
                                        if (entry.Key.gameObject == males[m].penisColliders[c])
                                        {
                                            // Set vagina insertion flag for consistency checking
                                            females[f].vaginaInsertionFlags[i] = true;

                                            if (c == (males[m].penisNames.Length - 1))
                                            {
                                                females[f].vaginaTipInsertionFlags[i] = true;
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // Consistency checking to ensure the penis is actually properly into the vagina
                        // Sometimes in the VAM environment the various rigidbodies and colliders can move through each other
                        // And this consistency checking avoids such spurious collisions from driving the robot in an uncontrolled manner
                        bool penisInserted = false;
                        int penisTipInsertionIndex = 0;

                        for (int i = 0; i < females[f].vaginaTriggers.Length; i++)
                        {
                            if (females[f].vaginaInsertionFlags[i])
                            {
                                for (int j = i; j >= 0; j--)
                                {
                                    if (females[f].vaginaInsertionFlags[j])
                                    {
                                        penisInserted = true;

                                        penisTipInsertionIndex = i;
                                    }
                                }
                            }
                            else
                            {
                                break;
                            }
                        }

                        // If the male's penis's tip collider wasn't triggering the furthest trigger in the female's vagina then the male's penis isn't inserted
                        if (!females[f].vaginaTipInsertionFlags[penisTipInsertionIndex])
                        {
                            penisInserted = false;
                        }

                        // Reset the vagina insertion and tip insertion flags
                        for (int i = 0; i < females[f].vaginaTriggers.Length; i++)
                        {
                            females[f].vaginaInsertionFlags[i] = false;

                            females[f].vaginaTipInsertionFlags[i] = false;
                        }

                        // If the penis is inserted into the vagina
                        if (penisInserted)
                        {
                            // Setup T-code reference coordinate system
                            // X(L0) is up/down in reference to the selected male's penis vector and is positive up
                            // Y(L1) is toward/away orthogonal to the selected male's penis vector and is positive away
                            // Z(L2) is left/right orthogonal to the selected male's penis vector and is positive left

                            // Vector from the selected male's penis's base to tip colliders
                            Vector3 refAxisX = males[m].penisVector;

                            // Use the vector from male's abdomenControl Rigidbody to the male's penis's base collider to establish the Z reference axis
                            Vector3 refAxisZ = Vector3.Cross(refAxisX, males[m].abdomen - males[m].penis[0]);
                            refAxisZ = (refAxisX.magnitude / refAxisZ.magnitude) * refAxisZ;

                            // Use the reference X and Z axes to establish the orthogonal Y axis
                            Vector3 refAxisY = Vector3.Cross(refAxisX, refAxisZ);
                            refAxisY = (refAxisX.magnitude / refAxisY.magnitude) * refAxisY;

                            // Vector from the female's vagina's labia trigger to the male's penis's base collider
                            Vector3 vaginaLabiaToPenisBase = females[f].vagina[0] - males[m].penis[0];

                            // Calculate X(L0) for robot based on the reference X axis and the vector from the female's vagina's labia trigger to the male's penis's base collider
                            float robotX = Vector3.Dot(refAxisX, vaginaLabiaToPenisBase) / (refAxisX.magnitude * refAxisX.magnitude);

                            // Calculate Y(L1) for robot based on the reference Y axis and the vector from the female's vagina's labia trigger to the male's penis's base collider
                            float robotY = 0.5f + Vector3.Dot(refAxisY, vaginaLabiaToPenisBase) / (refAxisX.magnitude * refAxisX.magnitude);

                            // Calculate Z(L2) for robot based on the reference Z axis and the vector from the female's vagina's labia trigger to the male's penis's base collider
                            float robotZ = 0.5f + Vector3.Dot(refAxisZ, vaginaLabiaToPenisBase) / (refAxisX.magnitude * refAxisX.magnitude);

                            // Vector from the female's vagina's labia to vagina triggers
                            Vector3 vaginaLabiaToVaginaTrigger = females[f].vagina[0] - females[f].vagina[1];

                            // Calculate RY(R1) for robot based on the reference Z axis and the vector from the female's vagina's labia to vagina triggers
                            float robotRYAngle = 90.0f - Vector3.Angle(refAxisZ, vaginaLabiaToVaginaTrigger);
                            float robotRY = 0.5f + robotRYAngle / 180.0f;

                            // Calculate RZ(R2) for robot based on the reference Y axis and the vector from the female's vagina's labia to vagina triggers
                            float robotRZAngle = -(90.0f - Vector3.Angle(refAxisY, vaginaLabiaToVaginaTrigger));
                            float robotRZ = 0.5f + robotRZAngle / 180.0f;

                            //string diagnostics = "Robot X(L0): " + robotX + "\n";
                            //diagnostics += "Robot Y(L1): " + robotY + "\n";
                            //diagnostics += "Robot Z(L2): " + robotZ + "\n";
                            //diagnostics += "Robot RY(R1): " + robotRY + "\n";
                            //diagnostics += "Robot RZ(R2): " + robotRZ + "\n";
                            //diagnostics += "Robot RY(R1) Angle: " + robotRYAngle + "\n";
                            //diagnostics += "Robot RZ(R2) Angle: " + robotRZAngle;
                            //SuperController.LogMessage(diagnostics);

                            int funscriptTime = (int)(((float)frameCounter * 1000.0f) / (float)frameRate);

                            funscriptAxisL0.Record((int)(robotX * 100.0f), funscriptTime);

                            if (multiaxis)
                            {
                                funscriptAxisL1.Record((int)(robotY * 100.0f), funscriptTime);
                                funscriptAxisL2.Record((int)(robotZ * 100.0f), funscriptTime);
                                funscriptAxisR1.Record((int)(robotRY * 100.0f), funscriptTime);
                                funscriptAxisR2.Record((int)(robotRZ * 100.0f), funscriptTime);
                            }
                        }

                        // Loop through the mouth triggers and look for any collisions between them and any other colliders in the scene
                        for (int i = 0; i < females[f].mouthTriggers.Length; i++)
                        {
                            Dictionary<Collider, bool> mouthDictionary = females[f].mouthRigidbodies[i].GetComponent<CollisionTriggerEventHandler>().collidingWithDictionary;

                            // Check for any collisions, zero if no collisions currently occurring
                            if (mouthDictionary.Count > 0)
                            {
                                foreach (KeyValuePair<Collider, bool> entry in mouthDictionary)
                                {
                                    // Loop through penis colliders
                                    for (int c = 0; c < males[m].penisNames.Length; c++)
                                    {
                                        // Check if one of the penis colliders is having a collision with the current female's mouth trigger
                                        //if (entry.Key.gameObject.name == males[m].penisNames[c])
                                        //{
                                        if (entry.Key.gameObject == males[m].penisColliders[c])
                                        {
                                            // Set mouth insertion flag for consistency checking
                                            females[f].mouthInsertionFlags[i] = true;

                                            if (c == (males[m].penisNames.Length - 1))
                                            {
                                                females[f].mouthTipInsertionFlags[i] = true;
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // Consistency checking to ensure the penis is actually properly into the mouth
                        // Sometimes in the VAM environment the various rigidbodies and colliders can move through each other
                        // And this consistency checking avoids such spurious collisions from driving the robot in an uncontrolled manner
                        penisInserted = false;
                        penisTipInsertionIndex = 0;

                        for (int i = 0; i < females[f].mouthTriggers.Length; i++)
                        {
                            if (females[f].mouthInsertionFlags[i])
                            {
                                for (int j = i; j >= 0; j--)
                                {
                                    if (females[f].mouthInsertionFlags[j])
                                    {
                                        penisInserted = true;

                                        penisTipInsertionIndex = i;
                                    }
                                }
                            }
                            else
                            {
                                break;
                            }
                        }

                        // If the male's penis's tip collider wasn't triggering the furthest trigger in the female's mouth then the male's penis isn't inserted
                        if (!females[f].mouthTipInsertionFlags[penisTipInsertionIndex])
                        {
                            penisInserted = false;
                        }

                        // Reset the mouth insertion  and tip insertion flags
                        for (int i = 0; i < females[f].mouthTriggers.Length; i++)
                        {
                            females[f].mouthInsertionFlags[i] = false;

                            females[f].mouthTipInsertionFlags[i] = false;
                        }

                        // If the penis is inserted into the mouth
                        if (penisInserted)
                        {
                            // Setup T-code reference coordinate system
                            // X(L0) is up/down in reference to the selected male's penis vector and is positive up
                            // Y(L1) is toward/away orthogonal to the selected male's penis vector and is positive away
                            // Z(L2) is left/right orthogonal to the selected male's penis vector and is positive left

                            // Vector from the selected male's penis's base to tip colliders
                            Vector3 refAxisX = males[m].penisVector;

                            // Use the vector from male's abdomenControl Rigidbody to the male's penis's base collider to establish the Z reference axis
                            Vector3 refAxisZ = Vector3.Cross(refAxisX, males[m].abdomen - males[m].penis[0]);
                            refAxisZ = (refAxisX.magnitude / refAxisZ.magnitude) * refAxisZ;

                            // Use the reference X and Z axes to establish the orthogonal Y axis
                            Vector3 refAxisY = Vector3.Cross(refAxisX, refAxisZ);
                            refAxisY = (refAxisX.magnitude / refAxisY.magnitude) * refAxisY;

                            // Vector from the female's mouth's lip trigger to the male's penis's base collider
                            Vector3 mouthLipToPenisBase = females[f].mouth[0] - males[m].penis[0];

                            // Calculate X(L0) for robot based on the reference X axis and the vector from the female's mouth's lip trigger to the male's penis's base collider
                            float robotX = Vector3.Dot(refAxisX, mouthLipToPenisBase) / (refAxisX.magnitude * refAxisX.magnitude);

                            // Calculate Y(L1) for robot based on the reference Y axis and the vector from the female's mouth's lip trigger to the male's penis's base collider
                            float robotY = 0.5f + Vector3.Dot(refAxisY, mouthLipToPenisBase) / (refAxisX.magnitude * refAxisX.magnitude);

                            // Calculate Z(L2) for robot based on the reference Z axis and the vector from the female's mouth's lip trigger to the male's penis's base collider
                            float robotZ = 0.5f + Vector3.Dot(refAxisZ, mouthLipToPenisBase) / (refAxisX.magnitude * refAxisX.magnitude);

                            // Vector from the female's mouth's lip to mouth triggers
                            Vector3 mouthLipToMouthTrigger = females[f].mouth[0] - females[f].mouth[1];

                            // Calculate RY(R1) for robot based on the reference Z axis and the vector from the female's mouth's lip to mouth triggers
                            float robotRYAngle = 90.0f - Vector3.Angle(refAxisZ, mouthLipToMouthTrigger);
                            float robotRY = 0.5f + robotRYAngle / 180.0f;

                            // Calculate RZ(R2) for robot based on the reference Y axis and the vector from the female's mouth's lip to mouth triggers
                            float robotRZAngle = -(90.0f - Vector3.Angle(refAxisY, mouthLipToMouthTrigger));
                            float robotRZ = 0.5f + robotRZAngle / 180.0f;

                            //string diagnostics = "Robot X(L0): " + robotX + "\n";
                            //diagnostics += "Robot Y(L1): " + robotY + "\n";
                            //diagnostics += "Robot Z(L2): " + robotZ + "\n";
                            //diagnostics += "Robot RY(R1): " + robotRY + "\n";
                            //diagnostics += "Robot RZ(R2): " + robotRZ + "\n";
                            //diagnostics += "Robot RY(R1) Angle: " + robotRYAngle + "\n";
                            //diagnostics += "Robot RZ(R2) Angle: " + robotRZAngle;
                            //SuperController.LogMessage(diagnostics);

                            int funscriptTime = (int)(((float)frameCounter * 1000.0f) / (float)frameRate);

                            funscriptAxisL0.Record((int)(robotX * 100.0f), funscriptTime);

                            if (multiaxis)
                            {
                                funscriptAxisL1.Record((int)(robotY * 100.0f), funscriptTime);
                                funscriptAxisL2.Record((int)(robotZ * 100.0f), funscriptTime);
                                funscriptAxisR1.Record((int)(robotRY * 100.0f), funscriptTime);
                                funscriptAxisR2.Record((int)(robotRZ * 100.0f), funscriptTime);
                            }
                        }
                    }
                }
            }

            return "";
        }

        public void MaleChooserCallback(string male)
        {
            SuperController.LogMessage(male + " selected.");
        }

        public void WriteFunscripts(string path)
        {
            funscriptAxisL0.Write(path);

            if (multiaxis)
            {
                funscriptAxisL1.Write(path);
                funscriptAxisL2.Write(path);
                funscriptAxisR1.Write(path);
                funscriptAxisR2.Write(path);
            }
        }
    }

    // Class for funscript axes
    public class FunscriptAxis
    {
        public string funscript = "";
        public int lastValue = 0;
        public string axis = "";

        public FunscriptAxis(string a)
        {
            axis = a;
            funscript = "{\"version\": \"1.0\",\"range\": 90,\"inverted\": false,\"actions\":[";
        }

        public void Record(int value, int time)
        {
            if (value < 0) value = 0;
            if (value > 100) value = 100;
            funscript += "{\"pos\": " + value + ",\"at\": " + time + "},";
            lastValue = value;
        }

        public string GetFunscript()
        {
            return funscript.Trim(',') + "]}";
        }

        public void Write(string path)
        {
            FileManagerSecure.WriteAllText(path + "." + axis + ".funscript", GetFunscript());
        }

        public void Reset()
        {
            funscript = "{\"version\": \"1.0\",\"range\": 90,\"inverted\": false,\"actions\":[";
            lastValue = 0;
        }
    }

    // Class for the females
    public class Female
    {
        public string name;
        public Vector3[] vagina;
        public Vector3[] mouth;
        public Vector3 vaginaVector;
        public Vector3 mouthVector;
        public string[] vaginaTriggers = { "LabiaTrigger", "VaginaTrigger", "DeepVaginaTrigger", "DeeperVaginaTrigger" };
        public string[] mouthTriggers = { "LipTrigger", "MouthTrigger", "ThroatTrigger" };
        public bool[] vaginaInsertionFlags;
        public bool[] mouthInsertionFlags;
        public bool[] vaginaTipInsertionFlags;
        public bool[] mouthTipInsertionFlags;
        public Rigidbody[] vaginaRigidbodies;
        public Rigidbody[] mouthRigidbodies;
        public List<Rigidbody[]> femaleRigidbodies;

        public Female(string female)
        {
            name = female;

            vagina = new Vector3[vaginaTriggers.Length];

            mouth = new Vector3[mouthTriggers.Length];

            vaginaRigidbodies = new Rigidbody[vaginaTriggers.Length];

            vaginaInsertionFlags = new bool[vaginaTriggers.Length];

            vaginaTipInsertionFlags = new bool[vaginaTriggers.Length];

            for (int i = 0; i < vaginaTriggers.Length; i++)
            {
                vaginaRigidbodies[i] = SuperController.singleton.GetAtomByUid(female).rigidbodies.First(rb => rb.name == vaginaTriggers[i]);

                vaginaInsertionFlags[i] = false;
            }

            mouthRigidbodies = new Rigidbody[mouthTriggers.Length];

            mouthInsertionFlags = new bool[mouthTriggers.Length];

            mouthTipInsertionFlags = new bool[mouthTriggers.Length];

            for (int i = 0; i < mouthTriggers.Length; i++)
            {
                mouthRigidbodies[i] = SuperController.singleton.GetAtomByUid(female).rigidbodies.First(rb => rb.name == mouthTriggers[i]);

                mouthInsertionFlags[i] = false;
            }
        }

        public void update()
        {
            for (int i = 0; i < vaginaTriggers.Length; i++)
            {
                vagina[i] = vaginaRigidbodies[i].position;
            }

            vaginaVector = vagina[0] - vagina[vaginaTriggers.Length - 1];

            for (int i = 0; i < mouthTriggers.Length; i++)
            {
                mouth[i] = mouthRigidbodies[i].position;
            }

            mouthVector = mouth[0] - mouth[mouthTriggers.Length - 1];
        }
    }

    // Class for the males
    public class Male
    {
        public string name;
        public Vector3[] penis;
        public Vector3 penisVector;
        public string[] penisNames = { "AutoColliderGen1Hard", "AutoColliderGen2Hard", "AutoColliderGen3aHard", "AutoColliderGen3bHard" };
        public GameObject[] penisColliders;
        public Rigidbody abdomenControl;
        public Vector3 abdomen;

        public Male(string male)
        {
            name = male;

            penis = new Vector3[penisNames.Length];

            penisColliders = new GameObject[penisNames.Length];

            for (int i = 0; i < penisNames.Length; i++)
            {
                foreach (Collider c in SuperController.singleton.GetAtomByUid(male).gameObject.GetComponentsInChildren<Collider>())
                {
                    if (c.gameObject.name == penisNames[i])
                    {
                        penisColliders[i] = c.gameObject;
                    }
                }
            }

            abdomenControl = new Rigidbody();

            abdomenControl = SuperController.singleton.GetAtomByUid(male).rigidbodies.First(rb => rb.name == "abdomenControl");
        }

        public void update()
        {
            for (int i = 0; i < penisNames.Length; i++)
            {
                penis[i] = penisColliders[i].transform.position;
            }

            penisVector = penis[penisNames.Length - 1] - penis[0];

            abdomen = abdomenControl.transform.position;
        }
    }
}
