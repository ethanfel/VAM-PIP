using System;
using System.Collections;
using System.Collections.Generic;
using MVR.FileManagementSecure;
using SimpleJSON;
using UnityEngine;

namespace VAMPip
{
    /// <summary>
    /// Narrow session-plugin bridge between VAM-PIP and VaM.
    ///
    /// The manager owns package and dependency changes. The bridge accepts a
    /// package rescan, one allowlisted resource load, or one bounded atom
    /// action at a time.
    /// </summary>
    public class VAMPipBridge : MVRScript
    {
        private const int ProtocolVersion = 2;
        private const string BridgeVersion = "1.0.0";
        private const int TimelineProtocolVersion = 1;
        private const int Sam3dSolutionSchema = 1;

        private const string PluginDataRoot = "Saves\\PluginData";
        private const string DataRoot = "Saves\\PluginData\\VAMPip";
        private const string BridgeRoot = DataRoot + "\\Bridge";
        private const string RequestPath = BridgeRoot + "\\request.json";
        private const string StatusPath = BridgeRoot + "\\status.json";
        private const string ScenePath = BridgeRoot + "\\scene.json";
        private const string TimelinePath = BridgeRoot + "\\timeline.json";
        private const string Sam3dRoot = DataRoot + "\\SAM3D";
        private const string Sam3dCameraPreset =
            "Custom/Atom/Empty/Preset_VAMPipSAM3DCamera.vap";
        private const string Sam3dReferenceUid =
            "VAMPip SAM3D Reference";
        private const string Sam3dReferenceAtomType =
            "ImagePanelEmissive";
        private const string Sam3dReferencePrefix =
            "Custom/Images/VAMPip/SAM3D/";

        private const int MaximumResourceRefLength = 1000;
        private const int MaximumCuaChoicesPerAtom = 128;
        private const int MaximumCuaChoicesGlobally = 512;
        private const int MaximumCuaChoiceLabelLength = 256;
        private const int MaximumClothingRefsPerPerson = 256;
        private const int MaximumClothingRefsGlobally = 1024;
        private const int MaximumHairItemsPerPerson = 128;
        private const int MaximumHairItemsGlobally = 512;
        private const int MaximumBodyProportionMorphs = 32;
        private const int MaximumBodyProportionChanges = 16;
        private const int MaximumRosterDisplayNameLength = 256;
        private const int MaximumRosterTagLength = 100;
        private const int MaximumRosterTagsPerItem = 32;
        private const int MaximumTimelineInstances = 32;
        private const int MaximumTimelineSegments = 64;
        private const int MaximumTimelineLayers = 128;
        private const int MaximumTimelineClips = 256;
        private const int MaximumTimelineClipsGlobally = 1024;
        private const int MaximumTimelineLabelLength = 256;
        private const int MaximumTimelineQualifiedLength = 512;
        private const int Sam3dControllerCount = 19;
        private const int Sam3dDiagnosticControllerCount = 2;
        private const int Sam3dDiagnosticSchema = 1;
        private const int Sam3dPhysicsResetFrames = 5;
        private const float MaximumSam3dCoordinate = 10.0f;
        private const float Sam3dCaptureWaitSeconds = 300.0f;
        private const int Sam3dReferenceMaximumBytes =
            32 * 1024 * 1024;
        private const int Sam3dReferenceMaximumDimension = 32768;
        private const float Sam3dReferenceDepthMargin = 0.25f;
        private const float Sam3dReferenceMaximumDepth = 25.0f;
        private const float Sam3dReferenceMaximumSize = 50.0f;
        private const float PollIntervalSeconds = 0.5f;
        private const float ScenePublishIntervalSeconds = 1.0f;
        private const float TimelinePublishIntervalSeconds = 1.0f;
        private const float MinimumRescanIntervalSeconds = 5.0f;
        private const float MaximumOperationWaitSeconds = 120.0f;
        private const float MaximumBodyProportionMagnitude = 1.0f;
        private const float MaximumBodyProportionDelta = 0.25f;
        private const float BodyShapeResponseStep = 0.1f;
        private const float BodyShapeLoopJoinTolerance = 0.00025f;
        private const float BodyShapeBustFirstFraction = 0.58f;
        private const float BodyShapeBustLastFraction = 0.76f;
        private const float BodyShapeWaistFirstFraction = 0.34f;
        private const float BodyShapeWaistLastFraction = 0.58f;
        private const float BodyShapeSeatFirstFraction = -0.08f;
        private const float BodyShapeSeatLastFraction = 0.12f;
        private const float BodyShapeUpperThighLegFraction = 0.35f;
        private const float BodyShapeBuildFrameBudgetSeconds = 0.003f;
        private const int BodyShapeBuildMaximumStepsPerFrame = 1;

        private const string CommandRescan = "rescan";
        private const string CommandApplyPersonPreset = "applyPersonPreset";
        private const string CommandAddPerson = "addPerson";
        private const string CommandAddAtom = "addAtom";
        private const string CommandApplyAtomPreset = "applyAtomPreset";
        private const string CommandLoadSubscene = "loadSubscene";
        private const string CommandLoadCustomUnityAsset =
            "loadCustomUnityAsset";
        private const string CommandSelectCustomUnityAssetChoice =
            "selectCustomUnityAssetChoice";
        private const string CommandSetPersonClothingResource =
            "setPersonClothingResource";
        private const string CommandSetPersonHairItem =
            "setPersonHairItem";
        private const string CommandSetPersonBodyProportions =
            "setPersonBodyProportions";
        private const string CommandUndoPersonBodyProportions =
            "undoPersonBodyProportions";
        private const string CommandSelectPerson = "selectPerson";
        private const string CommandSelectAtom = "selectAtom";
        private const string CommandLoadScene = "loadScene";
        private const string CommandControlTimeline = "controlTimeline";
        private const string CommandApplySam3dResult = "applySam3dResult";
        private const string CommandUndoSam3dResult = "undoSam3dResult";
        private const string CommandCaptureSam3dResult =
            "captureSam3dResult";
        private const string CommandShowSam3dReference =
            "showSam3dReference";
        private const string CommandRemoveSam3dReference =
            "removeSam3dReference";
        private const string Sam3dCoordinateSpace =
            "selected-person-hip-relative";
        private const string Sam3dRendererSuffix = "_Eosin.VRRenderer";
        private const string Sam3dCaptureAction = "VAMPipCapture";
        private const string Sam3dRequestIdParam = "VAMPipRequestId";
        private const string Sam3dBaseFilenameParam =
            "VAMPipBaseFilename";
        private const string Sam3dStatusParam = "VAMPipStatus";
        private const string Sam3dLastOutputParam = "VAMPipLastOutput";
        private const string Sam3dErrorParam = "VAMPipError";
        private const string TimelineExternalState =
            "VAM-PIP External State";
        private const string TimelineExternalCommand =
            "VAM-PIP External Command";
        private const string TimelineExternalResult =
            "VAM-PIP External Result";
        private const string TimelineRefreshExternalState =
            "VAM-PIP Refresh External State";
        private const string TimelineExecuteExternalCommand =
            "VAM-PIP Execute External Command";
        private const string StateQueued = "queued";
        private const string StateDeferredLoading = "deferred-loading";
        private const string StateRescanning = "rescanning";
        private const string StateApplying = "applying";
        private const string StateAdding = "adding";
        private const string StateSelecting = "selecting";
        private const string StateLoadingScene = "loading-scene";
        private const string StateApplyingSam3d = "applying-sam3d";
        private const string StateCapturingSam3d = "capturing-sam3d";
        private const string StateOk = "ok";
        private const string StateError = "error";
        private static readonly string[] BodyShapeMetricNames =
            new string[]
            {
                "bustGirth",
                "bustWidth",
                "bustDepth",
                "underbustGirth",
                "underbustWidth",
                "underbustDepth",
                "breastGirthExcess",
                "breastDepthExcess",
                "breastProjection",
                "waistGirth",
                "waistWidth",
                "waistDepth",
                "seatGirth",
                "seatWidth",
                "seatDepth",
                "gluteProjection",
                "upperThighGirth",
                "upperThighWidth",
                "upperThighDepth"
            };

        // VaM 1.22 native non-Person atom types, audited against
        // BrowserAssist 39's static native-type registry. Custom/package atom
        // types are intentionally browse-only: this must not become an
        // arbitrary AddAtomByType surface.
        private const string AllowedAtomTypes =
            "|AnimationPattern|AnimationStep|AptBook01|AptBook02|" +
            "AptBookShelf|AptChair|AptCoffeeTable|AptJacuzzi|" +
            "AptJacuzziProp|AptJacuzziRailing|AptLamp|AptOutdoorLight|" +
            "AptPatioChair|AptPicture01|AptPicture02|AptPlant|AptPlanter|" +
            "AptRug|AptSmartTV|AptSmartWebTV|AptSofa|AptSpeaker|AptTVStand|" +
            "AudioSource|Button|Capsule|CityScape|CityScapeNight|" +
            "ClothGrabSphere|CollisionTrigger|Crypt|Cube|CustomUnityAsset|" +
            "CyberpunkApartment|CyberpunkApartmentDecor|CyberpunkBed|" +
            "CyberpunkBedPillow01|CyberpunkBedPillow02|" +
            "CyberpunkBedPillow03|CyberpunkChair|CyberpunkCoffeeTable|" +
            "CyberpunkComputer|CyberpunkComputerChair|" +
            "CyberpunkControlScreen|CyberpunkDresser01|" +
            "CyberpunkDresser02|CyberpunkKeyboard|CyberpunkLaptop|" +
            "CyberpunkLight|CyberpunkMouse|CyberpunkMousepad|" +
            "CyberpunkRemote|CyberpunkSofa|CyberpunkSofaCushion01|" +
            "CyberpunkSofaCushion02|CyberpunkTable|CyberpunkTablet|" +
            "CyberpunkWallLight01|CyberpunkWallLight02|CycleForce|" +
            "DecoDowntimeChair|DecoDowntimeCoffeeTable|" +
            "DecoDowntimeSideTable|DecoDowntimeStand|Dildo|DreamHomeTV|" +
            "DreamHomeWebTV|DreamStreetBedroom|DSBR_2TierTable|DSBR_Bed|" +
            "DSBR_BedPillow|DSBR_Bench|DSBR_BuiltInShelves|DSBR_Chair|" +
            "DSBR_DecorativePillow|DSBR_Ottoman|DSBR_Shelf|" +
            "DSBR_ThrowPillow|Empty|Glass|Glass-Stained|GrabPoint|" +
            "ImagePanel|ImagePanelEmissive|ImagePanelTransparent|" +
            "ImagePanelTransparentEmissive|InvisibleLight|InvisiblePanel|" +
            "ISCapsule|ISCone|ISCube|ISCylinder|IslBench|IslFencePost|" +
            "IslFenceSection|IslOverlook|IslPatioChair|IslPlantWFlowers|" +
            "IslPotA|IslPotB|IslPotSmall|IslRailingGlass|IslStool|" +
            "IslTerrain|IslTopiary|IslTree|IslTreePlanter|IslWallPost|" +
            "IslWallSection|ISSphere|ISTube|LookAtTrigger|LoungeChair|" +
            "ModernRoomBed|ModernRoomLargeLamp|OldStyleBed|OldStyleChair|" +
            "OldStylePillow01|OldStylePillow02|OldStyleRoom|" +
            "OldStyleSideTable|OldStyleVanityStool|Paddle|" +
            "PlayerNavigationPanel|ReflectiveSlate|ReflectiveWoodPanel|" +
            "RhythmAudioSource|RhythmForce|SimpleSign|SimSheet|" +
            "SkullQueenSword|Slate|SpaceBox|Sphere|SubScene|SyncForce|" +
            "TechnoDancePole|TechnoGirder|TechnoLight|TechnoLightBar|" +
            "TechnoLightBar+Light|TechnoNeonCircle|" +
            "TechnoNeonCircle+Light|TechnoNeonHeart|" +
            "TechnoNeonHeart+Light|TechnoNeonSquare|" +
            "TechnoNeonSquare+Light|TechnoNeonTriangle|" +
            "TechnoNeonTriangle+Light|TechnoRingLight|" +
            "TechnoRingLight+Light|TechnoRoom|TechnoRoundCage|" +
            "TechnoRoundPlatform|TechnoThrone|Torch|ToyAH|ToyBP|UIButton|" +
            "UISlider|UIText|UIToggle|VaMLogo|VaMSign|VariableTrigger|" +
            "Wall|WebBrowser|WebPanel|WebPanelEmissive|WindowCamera|" +
            "WoodPanel|";

        private sealed class BridgeRequest
        {
            public string RequestId;
            public string Command;
            public string BrowserAssistMode;
            public string TargetUid;
            public string AtomType;
            public string PresetKind;
            public string ResourceRef;
            public bool RescanRequired;
            public bool Merge;
            public bool CreateIfMissing;
            public int ChoiceIndex;
            public string ChoiceToken;
            public bool ClothingActive;
            public string ClothingRevision;
            public string HairRevision;
            public string HairActionToken;
            public string BodyProportionRevision;
            public List<BodyProportionChange> BodyProportionChanges;
            public string TimelineId;
            public string TimelineRevision;
            public string TimelineOperation;
            public string TimelineItemToken;
            public float TimelineNumberValue;
            public bool TimelineBoolValue;
            public bool HasTimelineValue;
            public string Sam3dJobId;
            public string Sam3dRevision;
            public string Sam3dSolutionSha256;
            public string Sam3dCameraUid;
            public bool Sam3dCreateCamera;
            public string Sam3dExpectedJobRevision;
            public string Sam3dReferenceResourceRef;
            public string Sam3dReferenceSha256;
            public int Sam3dReferenceWidth;
            public int Sam3dReferenceHeight;
            public bool Sam3dKeepReference;
        }

        private sealed class BodyProportionChange
        {
            public string Key;
            public float Value;
        }

        private sealed class Sam3dControllerSolution
        {
            public string Id;
            public Vector3 Position;
            public Quaternion Rotation;
        }

        private sealed class Sam3dCameraSolution
        {
            public Vector3 Position;
            public Quaternion Rotation;
            public float FlatHorizontalFov;
            public string AspectRatio;
            public string OutputResolution;
            public string ImageFormat;
            public string BaseFilename;
        }

        private sealed class Sam3dSolution
        {
            public string JobId;
            public string Revision;
            public List<Sam3dControllerSolution> Controllers;
            public Sam3dCameraSolution Camera;
        }

        private sealed class Sam3dControllerDiagnostic
        {
            public string Id;
            public bool RequestedCaptured;
            public Vector3 RequestedPosition;
            public Quaternion RequestedRotation;
            public bool ActualCaptured;
            public Vector3 ActualPosition;
            public Quaternion ActualRotation;
            public FreeControllerV3.PositionState PositionState;
            public FreeControllerV3.RotationState RotationState;
            public bool PhysicsEnabled;
            public bool Possessed;
            public bool StartedPossess;
            public bool IsGrabbing;
        }

        private sealed class Sam3dApplyDiagnostics
        {
            public string RequestId;
            public string CapturedAtUtc;
            public string Error;
            public List<Sam3dControllerDiagnostic> Controllers;
        }

        private sealed class Sam3dControllerUndo
        {
            public FreeControllerV3 Controller;
            public Vector3 Position;
            public Quaternion Rotation;
            public FreeControllerV3.PositionState PositionState;
            public FreeControllerV3.RotationState RotationState;
            public bool PhysicsEnabled;
            public Rigidbody PhysicalBody;
            public bool PhysicalBodyWasPresent;
            public bool PhysicalBodyKinematic;
        }

        private sealed class Sam3dUndoSnapshot
        {
            public string JobId;
            public string Revision;
            public string TargetUid;
            public string CameraUid;
            public bool CameraCreated;
            public Atom Person;
            public bool PersonCollisionEnabled;
            public List<Sam3dControllerUndo> Controllers;
            public FreeControllerV3 CameraController;
            public Vector3 CameraPosition;
            public Quaternion CameraRotation;
            public FreeControllerV3.PositionState CameraPositionState;
            public FreeControllerV3.RotationState CameraRotationState;
            public bool CameraPhysicsEnabled;
            public Rigidbody CameraPhysicalBody;
            public bool CameraPhysicalBodyWasPresent;
            public bool CameraPhysicalBodyKinematic;
            public bool HeadRequestedRotationCaptured;
            public Quaternion HeadRequestedRotation;
            public bool PersistentHeadLockActive;
            public MVRScript Renderer;
            public float FlatHorizontalFov;
            public string CameraTarget;
            public string AspectRatio;
            public string OutputResolution;
            public string RenderMode;
            public string ImageFormat;
            public bool GenerateFunscripts;
            public Sam3dApplyDiagnostics Diagnostics;
            public Sam3dReferenceSnapshot Reference;
            public Sam3dReferenceState PreviousReferenceState;
        }

        private sealed class Sam3dReferenceSnapshot
        {
            public Atom Atom;
            public bool Created;
            public bool On;
            public bool CollisionEnabled;
            public FreeControllerV3 Controller;
            public Vector3 Position;
            public Quaternion Rotation;
            public FreeControllerV3.PositionState PositionState;
            public FreeControllerV3.RotationState RotationState;
            public bool PhysicsEnabled;
            public Rigidbody PhysicalBody;
            public bool PhysicalBodyWasPresent;
            public bool PhysicalBodyKinematic;
            public JSONStorableUrl Url;
            public string UrlValue;
            public JSONStorableFloat Scale;
            public float ScaleValue;
            public JSONStorableFloat ScaleX;
            public float ScaleXValue;
            public JSONStorableFloat ScaleY;
            public float ScaleYValue;
            public JSONStorableFloat ScaleZ;
            public float ScaleZValue;
        }

        private sealed class Sam3dReferenceState
        {
            public Atom Atom;
            public string JobId;
            public string JobRevision;
            public string SolutionRevision;
            public string TargetUid;
            public string ResourceRef;
            public string ResourceSha256;
            public int SourceWidth;
            public int SourceHeight;
            public bool AlignedToPose;
        }

        private sealed class Sam3dReferenceResult
        {
            public Atom Atom;
            public bool Created;
            public string Error;
        }

        private sealed class Sam3dCameraResult
        {
            public Atom Atom;
            public bool Created;
            public string Error;
        }

        private sealed class AtomCreationResult
        {
            public Atom Atom;
            public bool Created;
            public string Error;
        }

        private sealed class LoadingWaitResult
        {
            public string Error;
        }

        private sealed class CuaChoiceSnapshot
        {
            public Atom Atom;
            public CustomUnityAssetLoader Loader;
            public List<string> ChoiceList;
            public string GenerationKey;
            public string ChoiceToken;
            public List<int> PublishedIndices;
        }

        private sealed class CuaLoaderState
        {
            public CustomUnityAssetLoader Loader;
            public JSONStorableUrl AssetUrl;
            public JSONStorableStringChooser AssetName;
            public JSONStorableBool LoadDll;
            public string Error;
        }

        private sealed class ActiveClothingEntry
        {
            public DAZClothingItem Item;
            public string ResourceRef;
            public string Uid;
            public string InternalUid;
            public string PackageUid;
            public string DisplayName;
            public string[] Tags;
            public bool Locked;
        }

        private sealed class ActiveHairEntry
        {
            public DAZHairGroup Item;
            public string Uid;
            public string InternalUid;
            public string PackageUid;
            public string DisplayName;
            public string[] Tags;
            public bool Locked;
            public bool Simulated;
        }

        private sealed class PersonClothingSnapshot
        {
            public Atom Atom;
            public DAZCharacterSelector Geometry;
            public string GenerationKey;
            public string Revision;
        }

        private sealed class PersonHairSnapshot
        {
            public Atom Atom;
            public DAZCharacterSelector Geometry;
            public string GenerationKey;
            public string Revision;
            public List<DAZHairGroup> Items;
            public List<string> ActionTokens;
            public int PublishedCount;
        }

        private sealed class BodyProportionMorphEntry
        {
            public DAZMorph Morph;
            public DAZMorphBank Bank;
            public string Key;
            public string Name;
            public string Region;
            public string FitKind;
            public string ShapeRegion;
            public Dictionary<string, float> ShapeResponses;
            public float Value;
            public float Minimum;
            public float Maximum;
        }

        private sealed class BodyShapeMetric
        {
            public string Region;
            public float Meters;
            public bool Bilateral;
            public float LeftMeters;
            public float RightMeters;
        }

        private sealed class BodyShapeSignature
        {
            public float StructuralLength;
            public float BustTorsoFraction;
            public float UnderbustTorsoFraction;
            public float WaistTorsoFraction;
            public float SeatTorsoFraction;
            public float UpperThighLegFraction;
            public Dictionary<string, BodyShapeMetric> Measurements;
        }

        private sealed class BodyShapeSegment
        {
            public Vector2 First;
            public Vector2 Second;
            public bool Used;
        }

        private sealed class BodyShapeLoop
        {
            public List<Vector2> Points;
            public float Perimeter;
            public float Area;
            public float MinimumX;
            public float MaximumX;
            public float MinimumZ;
            public float MaximumZ;
            public Vector2 Centroid;
        }

        private sealed class BodyShapeSection
        {
            public float Girth;
            public float Width;
            public float Depth;
            public float MinimumX;
            public float MaximumX;
            public float MinimumZ;
            public float MaximumZ;
        }

        private sealed class BodyShapeFrame
        {
            public Vector3 Origin;
            public Vector3 Lateral;
            public Vector3 Up;
            public Vector3 Front;
            public Vector3 LeftThigh;
            public Vector3 RightThigh;
            public Vector3 LeftShin;
            public Vector3 RightShin;
            public float TorsoLength;
            public float HipToKnee;
            public float StructuralLength;
            public float ShoulderSpan;
        }

        private sealed class BodyShapeSignatureWork
        {
            public Vector3[] Vertices;
            public int[] Triangles;
            public BodyShapeFrame Frame;
            public float ScaleX;
            public float ScaleZ;
            public int Phase;
            public int ScanIndex;
            public bool Complete;
            public bool Failed;
            public BodyShapeSection Bust;
            public BodyShapeSection Underbust;
            public BodyShapeSection Waist;
            public BodyShapeSection Seat;
            public BodyShapeSection LeftThigh;
            public BodyShapeSection RightThigh;
            public float BustFraction;
            public float UnderbustFraction;
            public float WaistFraction;
            public float SeatFraction;
            public BodyShapeSignature Result;
        }

        private sealed class PersonBodyShapeCache
        {
            public Atom Atom;
            public DAZCharacterSelector Geometry;
            public string MeshChecksum;
            public BodyShapeSignature Signature;
            public Dictionary<
                DAZMorph,
                Dictionary<string, float>> Responses;
        }

        private sealed class PersonBodyShapeBuild
        {
            public Atom Atom;
            public DAZCharacterSelector Geometry;
            public string MeshChecksum;
            public Vector3[] Vertices;
            public int[] Triangles;
            public BodyShapeFrame Frame;
            public float ScaleX;
            public float ScaleZ;
            public List<BodyProportionMorphEntry> Entries;
            public bool Cancelled;
        }

        private sealed class PersonBodyProportionSnapshot
        {
            public Atom Atom;
            public DAZCharacterSelector Geometry;
            public string GenerationKey;
            public string Revision;
            public List<BodyProportionMorphEntry> Entries;
            public BodyShapeSignature BodyShape;
            public string BodyShapeMeshChecksum;
        }

        private sealed class BodyProportionUndoValue
        {
            public DAZMorph Morph;
            public float Value;
        }

        private sealed class PersonBodyProportionUndo
        {
            public Atom Atom;
            public DAZCharacterSelector Geometry;
            public string TargetUid;
            public string Revision;
            public string PostApplyMorphStateKey;
            public List<BodyProportionUndoValue> Values;
        }

        private sealed class TimelineItemSnapshot
        {
            public string Token;
            public int AdapterId;
            public int AdapterSegmentId;
            public int AdapterLayerId;
            public string Name;
            public string RawName;
            public string Qualified;
            public float Length;
            public float Time;
            public float Speed;
            public float Weight;
            public int TargetCount;
            public bool Loop;
            public bool Playing;
            public bool Main;
            public bool Selected;
        }

        private sealed class TimelineSnapshot
        {
            public Atom Atom;
            public MVRScript Plugin;
            public string StorableId;
            public string TimelineId;
            public string Revision;
            public string GenerationKey;
            public bool Enhanced;
            public int CatalogRevision;
            public List<TimelineItemSnapshot> Segments;
            public List<TimelineItemSnapshot> Layers;
            public List<TimelineItemSnapshot> Clips;
        }

        private sealed class TimelineCandidate
        {
            public int ScanIndex;
            public string Key;
            public Atom Atom;
            public MVRScript Plugin;
            public string StorableId;
            public bool Selected;
            public bool Playing;
            public bool AdapterAvailable;
            public JSONStorableString AdapterState;
            public JSONStorableAction AdapterRefresh;
            public JSONClass Result;
        }

        private bool _operational;
        private bool _requestInProgress;
        private bool _skipPendingProcessing;
        private float _nextPollAt;
        private float _nextScenePublishAt;
        private float _nextTimelinePublishAt;
        private float _nextAllowedRescanAt;
        private string _instanceId = "";
        private string _lastRequestPayload;
        private string _lastHandledRequestId = "";
        private string _lastCompletedRequestId = "";
        private string _lastPublishedStatusSignature = "";
        private string _mailboxRejectedRequestId = "";
        private string _mailboxRejectedMessage = "";
        private BridgeRequest _pendingRequest;
        private readonly Dictionary<string, CuaChoiceSnapshot>
            _cuaChoiceSnapshots =
                new Dictionary<string, CuaChoiceSnapshot>();
        private readonly Dictionary<string, PersonClothingSnapshot>
            _personClothingSnapshots =
                new Dictionary<string, PersonClothingSnapshot>();
        private readonly Dictionary<string, PersonHairSnapshot>
            _personHairSnapshots =
                new Dictionary<string, PersonHairSnapshot>();
        private readonly Dictionary<string, PersonBodyProportionSnapshot>
            _personBodyProportionSnapshots =
                new Dictionary<string, PersonBodyProportionSnapshot>();
        private readonly Dictionary<string, PersonBodyProportionUndo>
            _personBodyProportionUndo =
                new Dictionary<string, PersonBodyProportionUndo>();
        private readonly Dictionary<string, PersonBodyShapeCache>
            _personBodyShapeCaches =
                new Dictionary<string, PersonBodyShapeCache>();
        private readonly Dictionary<string, PersonBodyShapeBuild>
            _personBodyShapeBuilds =
                new Dictionary<string, PersonBodyShapeBuild>();
        private readonly Dictionary<string, TimelineSnapshot>
            _timelineSnapshots =
                new Dictionary<string, TimelineSnapshot>();
        private Sam3dUndoSnapshot _sam3dUndoSnapshot;
        private Sam3dReferenceState _sam3dReferenceState;
        private BridgeRequest _inFlightSam3dCameraRequest;
        private Sam3dCameraResult _inFlightSam3dCameraResult;
        private BridgeRequest _inFlightSam3dReferenceRequest;
        private Sam3dReferenceResult _inFlightSam3dReferenceResult;
        private string _lastSam3dRequestId = "";
        private string _lastSam3dCommand = "";
        private string _lastSam3dJobId = "";
        private string _lastSam3dRevision = "";
        private string _lastSam3dCameraUid = "";
        private string _lastSam3dState = "";
        private string _lastSam3dMessage = "";

        public override void Init()
        {
            try
            {
                _instanceId = Guid.NewGuid().ToString("N");
                EnsureBridgeDirectory();
                RecoverLastCompletedRequest();
                IgnoreCompletedLegacyRequest();

                if (containingAtom == null ||
                    containingAtom.name != "CoreControl" ||
                    containingAtom.type != "SessionPluginManager")
                {
                    const string message =
                        "VAM-PIP Bridge must be loaded from VaM's Session Plugins screen.";
                    PublishStatus(StateError, "", "", UtcNow(), "", message);
                    SuperController.LogError("[VAM-PIP Bridge] " + message);
                    return;
                }

                _operational = true;
                _nextPollAt = Time.realtimeSinceStartup + 0.25f;
                _nextScenePublishAt = Time.realtimeSinceStartup;
                _nextTimelinePublishAt = Time.realtimeSinceStartup;
                PublishStatus(
                    StateOk,
                    _lastCompletedRequestId,
                    "",
                    "",
                    "",
                    "Bridge ready.");
                PublishSceneStatus();
                PublishTimelineStatus();
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Ready. Watching " + RequestPath + ".");
            }
            catch (Exception exception)
            {
                _operational = false;
                string message = "Initialization failed: " + DescribeException(exception);
                PublishStatus(StateError, "", "", UtcNow(), "", message);
                SuperController.LogError("[VAM-PIP Bridge] " + message);
            }
        }

        private void OnDisable()
        {
            StopBridgeWorkForLifecycle("disabled");
        }

        private void OnDestroy()
        {
            _operational = false;
            StopBridgeWorkForLifecycle("destroyed");
        }

        private void StopBridgeWorkForLifecycle(
            string lifecycle)
        {
            BridgeRequest interruptedRequest = _pendingRequest;
            if (interruptedRequest == null)
            {
                interruptedRequest =
                    _inFlightSam3dCameraRequest;
            }
            if (interruptedRequest == null)
            {
                interruptedRequest =
                    _inFlightSam3dReferenceRequest;
            }
            bool requestInterrupted =
                _requestInProgress ||
                interruptedRequest != null ||
                _inFlightSam3dCameraResult != null ||
                _inFlightSam3dReferenceResult != null;
            StopAllCoroutines();
            _personBodyShapeBuilds.Clear();
            _requestInProgress = false;
            _pendingRequest = null;
            _skipPendingProcessing = false;
            _mailboxRejectedRequestId = "";
            _mailboxRejectedMessage = "";
            string referenceCleanupError =
                RemoveInFlightCreatedSam3dReference();
            string cameraCleanupError =
                RemoveInFlightCreatedSam3dCamera();
            ReleaseSam3dPoseLockWithoutRestoringPose(
                _sam3dUndoSnapshot,
                "plugin " + lifecycle);
            if (!requestInterrupted)
            {
                return;
            }

            string message =
                "Bridge request was cancelled because the VAM-PIP " +
                "session plugin was " +
                lifecycle +
                ".";
            if (referenceCleanupError.Length != 0)
            {
                message += referenceCleanupError;
            }
            if (cameraCleanupError.Length != 0)
            {
                message += cameraCleanupError;
            }
            try
            {
                if (interruptedRequest != null)
                {
                    if (interruptedRequest.Command ==
                            CommandApplySam3dResult ||
                        interruptedRequest.Command ==
                            CommandUndoSam3dResult ||
                        interruptedRequest.Command ==
                            CommandCaptureSam3dResult ||
                        interruptedRequest.Command ==
                            CommandShowSam3dReference ||
                        interruptedRequest.Command ==
                            CommandRemoveSam3dReference)
                    {
                        RecordSam3dAction(
                            interruptedRequest,
                            StateError,
                            message);
                    }
                    FailRequest(
                        interruptedRequest,
                        "",
                        message);
                }
                else
                {
                    PublishStatus(
                        StateError,
                        "",
                        "",
                        UtcNow(),
                        "",
                        message);
                    SuperController.LogError(
                        "[VAM-PIP Bridge] " + message);
                }
            }
            catch
            {
                // Physics cleanup and request normalization must still
                // complete while VaM is tearing the plugin down.
            }
        }

        private string RemoveInFlightCreatedSam3dCamera()
        {
            BridgeRequest request =
                _inFlightSam3dCameraRequest;
            Sam3dCameraResult result =
                _inFlightSam3dCameraResult;
            _inFlightSam3dCameraRequest = null;
            _inFlightSam3dCameraResult = null;
            if (request == null ||
                result == null ||
                !result.Created)
            {
                return "";
            }
            return RemoveCreatedSam3dCamera(request, result);
        }

        private void ClearInFlightSam3dCamera(
            BridgeRequest request,
            Sam3dCameraResult result)
        {
            if (object.ReferenceEquals(
                    _inFlightSam3dCameraRequest,
                    request) &&
                object.ReferenceEquals(
                    _inFlightSam3dCameraResult,
                    result))
            {
                _inFlightSam3dCameraRequest = null;
                _inFlightSam3dCameraResult = null;
            }
        }

        private string RemoveInFlightCreatedSam3dReference()
        {
            Sam3dReferenceResult result =
                _inFlightSam3dReferenceResult;
            _inFlightSam3dReferenceRequest = null;
            _inFlightSam3dReferenceResult = null;
            if (result == null ||
                !result.Created)
            {
                return "";
            }
            return RemoveCreatedSam3dReference(result);
        }

        private void ClearInFlightSam3dReference(
            BridgeRequest request,
            Sam3dReferenceResult result)
        {
            if (object.ReferenceEquals(
                    _inFlightSam3dReferenceRequest,
                    request) &&
                object.ReferenceEquals(
                    _inFlightSam3dReferenceResult,
                    result))
            {
                _inFlightSam3dReferenceRequest = null;
                _inFlightSam3dReferenceResult = null;
            }
        }

        private void Update()
        {
            if (!_operational)
            {
                return;
            }

            float now = Time.realtimeSinceStartup;
            if (now >= _nextScenePublishAt)
            {
                _nextScenePublishAt = now + ScenePublishIntervalSeconds;
                PublishSceneStatus();
            }
            if (now >= _nextTimelinePublishAt)
            {
                _nextTimelinePublishAt =
                    now + TimelinePublishIntervalSeconds;
                PublishTimelineStatus();
            }

            if (now < _nextPollAt)
            {
                return;
            }

            _nextPollAt = now + PollIntervalSeconds;
            _skipPendingProcessing = false;

            try
            {
                PollRequestFile();
                if (!_skipPendingProcessing)
                {
                    ProcessPendingRequest(now);
                }
                RestoreMailboxRejectionStatus();
            }
            catch (Exception exception)
            {
                string requestId =
                    _pendingRequest == null ? "" : _pendingRequest.RequestId;
                string message = "Bridge update failed: " + DescribeException(exception);
                PublishStatus(StateError, requestId, "", UtcNow(), "", message);
                SuperController.LogError("[VAM-PIP Bridge] " + message);
            }
        }

        private static string UtcNow()
        {
            return DateTime.UtcNow.ToString("O");
        }

        private static void EnsureDirectory(string path)
        {
            if (!FileManagerSecure.DirectoryExists(path))
            {
                FileManagerSecure.CreateDirectory(path);
            }
        }

        private static void EnsureBridgeDirectory()
        {
            EnsureDirectory(PluginDataRoot);
            EnsureDirectory(DataRoot);
            EnsureDirectory(BridgeRoot);
        }

        private void RecoverLastCompletedRequest()
        {
            if (!FileManagerSecure.FileExists(StatusPath))
            {
                return;
            }

            try
            {
                JSONClass status =
                    JSON.Parse(FileManagerSecure.ReadAllText(StatusPath)).AsObject;
                if (status == null || status["protocol"].AsInt != ProtocolVersion)
                {
                    return;
                }

                string requestId =
                    ((string)status["lastCompletedRequestId"] ?? "").Trim();
                if (requestId.Length == 0 &&
                    (string)status["state"] == StateOk)
                {
                    requestId = ((string)status["requestId"] ?? "").Trim();
                }
                if (requestId.Length == 0)
                {
                    return;
                }

                _lastHandledRequestId = requestId;
                _lastCompletedRequestId = requestId;
            }
            catch
            {
                // The external reader and this recovery path both retry after
                // a transient partial status write.
            }
        }

        private void IgnoreCompletedLegacyRequest()
        {
            if (!FileManagerSecure.FileExists(RequestPath) ||
                !FileManagerSecure.FileExists(StatusPath))
            {
                return;
            }

            try
            {
                string payload = FileManagerSecure.ReadAllText(RequestPath);
                JSONClass request = JSON.Parse(payload).AsObject;
                JSONClass status =
                    JSON.Parse(FileManagerSecure.ReadAllText(StatusPath)).AsObject;
                if (request == null || status == null)
                {
                    return;
                }

                int requestProtocol = request["protocol"].AsInt;
                if (requestProtocol <= 0 ||
                    requestProtocol >= ProtocolVersion ||
                    status["protocol"].AsInt != requestProtocol)
                {
                    return;
                }

                string requestId =
                    ((string)request["requestId"] ?? "").Trim();
                string completedRequestId =
                    ((string)status["lastCompletedRequestId"] ?? "").Trim();
                if (requestId.Length == 0 ||
                    !string.Equals(
                        requestId,
                        completedRequestId,
                        StringComparison.Ordinal))
                {
                    return;
                }

                // A completed request from an older bridge is historical
                // mailbox state, not work for this protocol generation.
                // Remember its exact payload so the first poll does not turn
                // a successful bridge upgrade into a spurious error.
                _lastRequestPayload = payload;
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Ignored completed protocol-" +
                    requestProtocol +
                    " mailbox request after upgrade.");
            }
            catch
            {
                // PollRequestFile will validate and report a malformed or
                // partially-written request once the bridge is operational.
            }
        }

        private void PollRequestFile()
        {
            if (!FileManagerSecure.FileExists(RequestPath))
            {
                return;
            }

            string payload = FileManagerSecure.ReadAllText(RequestPath);
            if (payload == _lastRequestPayload)
            {
                return;
            }
            _lastRequestPayload = payload;
            _mailboxRejectedRequestId = "";
            _mailboxRejectedMessage = "";

            string requestId = "";
            try
            {
                JSONClass request = JSON.Parse(payload).AsObject;
                if (request == null)
                {
                    RejectRequest("", "Request is not a JSON object.");
                    return;
                }

                requestId = ((string)request["requestId"] ?? "").Trim();
                if (request["protocol"].AsInt != ProtocolVersion)
                {
                    RejectRequest(requestId, "Unsupported bridge protocol.");
                    return;
                }
                if (requestId.Length == 0 || requestId.Length > 200)
                {
                    RejectRequest(
                        requestId,
                        "requestId must contain 1 to 200 characters.");
                    return;
                }

                if (_pendingRequest == null &&
                    requestId == _lastHandledRequestId)
                {
                    return;
                }

                string command = ((string)request["command"] ?? "").Trim();
                BridgeRequest parsed = new BridgeRequest();
                parsed.RequestId = requestId;
                parsed.Command = command;
                parsed.BrowserAssistMode = "auto";
                parsed.TargetUid = "";
                parsed.AtomType = "";
                parsed.PresetKind = "";
                parsed.ResourceRef = "";
                parsed.Merge = false;
                parsed.CreateIfMissing = false;
                parsed.ChoiceIndex = -1;
                parsed.ChoiceToken = "";
                parsed.ClothingActive = false;
                parsed.ClothingRevision = "";
                parsed.HairRevision = "";
                parsed.HairActionToken = "";
                parsed.BodyProportionRevision = "";
                parsed.BodyProportionChanges =
                    new List<BodyProportionChange>();
                parsed.TimelineId = "";
                parsed.TimelineRevision = "";
                parsed.TimelineOperation = "";
                parsed.TimelineItemToken = "";
                parsed.Sam3dJobId = "";
                parsed.Sam3dRevision = "";
                parsed.Sam3dSolutionSha256 = "";
                parsed.Sam3dCameraUid = "";
                parsed.Sam3dCreateCamera = false;
                parsed.Sam3dExpectedJobRevision = "";
                parsed.Sam3dReferenceResourceRef = "";
                parsed.Sam3dReferenceSha256 = "";
                parsed.Sam3dReferenceWidth = 0;
                parsed.Sam3dReferenceHeight = 0;
                parsed.Sam3dKeepReference = false;

                if (command == CommandRescan)
                {
                    string browserAssistMode =
                        ((string)request["browserAssist"] ?? "auto")
                        .Trim()
                        .ToLowerInvariant();
                    if (browserAssistMode.Length == 0)
                    {
                        browserAssistMode = "auto";
                    }
                    if (browserAssistMode != "auto" &&
                        browserAssistMode != "off")
                    {
                        RejectRequest(
                            requestId,
                            "browserAssist must be either 'auto' or 'off'.");
                        return;
                    }
                    parsed.BrowserAssistMode = browserAssistMode;
                    parsed.RescanRequired = true;
                }
                else if (command == CommandApplyPersonPreset)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.PresetKind =
                        ((string)request["presetKind"] ?? "").Trim();
                    parsed.ResourceRef =
                        (string)request["resourceRef"] ?? "";
                    parsed.RescanRequired = request["rescan"].AsBool;
                    parsed.Merge = request["merge"].AsBool;

                    string validationError = ValidateApplyRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandAddPerson ||
                         command == CommandSelectPerson ||
                         command == CommandSelectAtom)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    string validationError =
                        ValidateTargetUid(parsed.TargetUid);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                    parsed.RescanRequired = false;
                }
                else if (command == CommandAddAtom)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.AtomType =
                        (string)request["atomType"] ?? "";
                    string validationError =
                        ValidateAddAtomRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                    parsed.RescanRequired = false;
                }
                else if (command == CommandApplyAtomPreset)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.AtomType =
                        (string)request["atomType"] ?? "";
                    parsed.ResourceRef =
                        (string)request["resourceRef"] ?? "";
                    parsed.RescanRequired = request["rescan"].AsBool;
                    parsed.Merge = request["merge"].AsBool;
                    parsed.CreateIfMissing =
                        request["createIfMissing"].AsBool;

                    string validationError =
                        ValidateAtomPresetRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandLoadSubscene)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.AtomType = "SubScene";
                    parsed.ResourceRef =
                        (string)request["resourceRef"] ?? "";
                    parsed.RescanRequired = request["rescan"].AsBool;
                    parsed.CreateIfMissing =
                        request["createIfMissing"].AsBool;

                    string validationError =
                        ValidateSubsceneRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandLoadCustomUnityAsset)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.AtomType = "CustomUnityAsset";
                    parsed.ResourceRef =
                        (string)request["resourceRef"] ?? "";
                    parsed.RescanRequired = request["rescan"].AsBool;
                    parsed.CreateIfMissing =
                        request["createIfMissing"].AsBool;

                    string validationError =
                        ValidateCustomUnityAssetRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandSelectCustomUnityAssetChoice)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.AtomType = "CustomUnityAsset";
                    parsed.ChoiceIndex = request["choiceIndex"].AsInt;
                    parsed.ChoiceToken =
                        (string)request["choiceToken"] ?? "";
                    parsed.RescanRequired = false;

                    string validationError =
                        ValidateCustomUnityAssetChoiceRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandSetPersonClothingResource)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.ResourceRef =
                        (string)request["resourceRef"] ?? "";
                    parsed.ClothingRevision =
                        (string)request["revision"] ?? "";
                    parsed.RescanRequired = request["rescan"].AsBool;
                    string desiredState =
                        (string)request["desiredState"] ?? "";
                    if (desiredState == "worn")
                    {
                        parsed.ClothingActive = true;
                    }
                    else if (desiredState == "removed")
                    {
                        parsed.ClothingActive = false;
                    }
                    else
                    {
                        RejectRequest(
                            requestId,
                            "desiredState must be exactly 'worn' or 'removed'.");
                        return;
                    }

                    string validationError =
                        ValidatePersonClothingRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandSetPersonHairItem)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.HairRevision =
                        (string)request["revision"] ?? "";
                    parsed.HairActionToken =
                        (string)request["actionToken"] ?? "";
                    parsed.RescanRequired = false;
                    string desiredState =
                        (string)request["desiredState"] ?? "";
                    if (desiredState != "removed")
                    {
                        RejectRequest(
                            requestId,
                            "Hair desiredState must be exactly 'removed'.");
                        return;
                    }

                    string validationError =
                        ValidatePersonHairRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandSetPersonBodyProportions)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.BodyProportionRevision =
                        ((string)request["expectedRevision"] ?? "").Trim();
                    parsed.RescanRequired = false;
                    JSONArray changes = request["changes"].AsArray;
                    if (changes == null ||
                        changes.Count == 0 ||
                        changes.Count > MaximumBodyProportionChanges)
                    {
                        RejectRequest(
                            requestId,
                            "changes must contain 1 to " +
                            MaximumBodyProportionChanges +
                            " body-proportion updates.");
                        return;
                    }
                    int changeIndex;
                    for (changeIndex = 0;
                         changeIndex < changes.Count;
                         changeIndex++)
                    {
                        JSONClass changeNode =
                            changes[changeIndex].AsObject;
                        if (changeNode == null ||
                            !changeNode.HasKey("value"))
                        {
                            RejectRequest(
                                requestId,
                                "Each body-proportion change requires key and value.");
                            return;
                        }
                        BodyProportionChange change =
                            new BodyProportionChange();
                        change.Key =
                            ((string)changeNode["key"] ?? "").Trim();
                        change.Value = changeNode["value"].AsFloat;
                        parsed.BodyProportionChanges.Add(change);
                    }
                    string validationError =
                        ValidateBodyProportionRequest(parsed, false);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandUndoPersonBodyProportions)
                {
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.BodyProportionRevision =
                        ((string)request["expectedRevision"] ?? "").Trim();
                    parsed.RescanRequired = false;
                    string validationError =
                        ValidateBodyProportionRequest(parsed, true);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandLoadScene)
                {
                    parsed.ResourceRef =
                        (string)request["resourceRef"] ?? "";
                    parsed.RescanRequired = request["rescan"].AsBool;
                    parsed.Merge = request["merge"].AsBool;

                    string validationError =
                        ValidateSceneRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandControlTimeline)
                {
                    parsed.TimelineId =
                        ((string)request["timelineId"] ?? "").Trim();
                    parsed.TimelineRevision =
                        ((string)request["expectedRevision"] ?? "").Trim();
                    parsed.TimelineOperation =
                        ((string)request["operation"] ?? "").Trim();
                    parsed.RescanRequired = false;
                    parsed.HasTimelineValue = request.HasKey("value");

                    string itemField =
                        TimelineItemField(parsed.TimelineOperation);
                    if (itemField.Length != 0)
                    {
                        parsed.TimelineItemToken =
                            ((string)request[itemField] ?? "").Trim();
                    }
                    if (parsed.TimelineOperation == "setLocked")
                    {
                        parsed.TimelineBoolValue =
                            request["value"].AsBool;
                    }
                    else if (
                        parsed.TimelineOperation == "setTime" ||
                        parsed.TimelineOperation == "setSpeed" ||
                        parsed.TimelineOperation == "setWeight")
                    {
                        parsed.TimelineNumberValue =
                            request["value"].AsFloat;
                    }

                    string validationError =
                        ValidateTimelineRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandApplySam3dResult)
                {
                    parsed.Sam3dJobId =
                        ((string)request["jobId"] ?? "").Trim();
                    parsed.Sam3dRevision =
                        ((string)request["expectedRevision"] ?? "").Trim();
                    parsed.Sam3dSolutionSha256 =
                        ((string)request["solutionSha256"] ?? "").Trim();
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.Sam3dCameraUid =
                        ((string)request["cameraUid"] ?? "").Trim();
                    parsed.Sam3dCreateCamera =
                        request["createCamera"].AsBool;
                    parsed.Sam3dKeepReference =
                        request["keepReference"].AsBool;
                    if (parsed.Sam3dKeepReference)
                    {
                        ParseSam3dReferenceFields(request, parsed);
                    }
                    parsed.RescanRequired = false;

                    string validationError =
                        ValidateSam3dApplyRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandUndoSam3dResult)
                {
                    parsed.Sam3dJobId =
                        ((string)request["jobId"] ?? "").Trim();
                    parsed.Sam3dRevision =
                        ((string)request["expectedRevision"] ?? "").Trim();
                    parsed.RescanRequired = false;

                    string validationError =
                        ValidateSam3dIdentity(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandCaptureSam3dResult)
                {
                    parsed.Sam3dJobId =
                        ((string)request["jobId"] ?? "").Trim();
                    parsed.Sam3dRevision =
                        ((string)request["expectedRevision"] ?? "").Trim();
                    parsed.Sam3dSolutionSha256 =
                        ((string)request["solutionSha256"] ?? "").Trim();
                    parsed.Sam3dCameraUid =
                        ((string)request["cameraUid"] ?? "").Trim();
                    parsed.RescanRequired = false;

                    string validationError =
                        ValidateSam3dCaptureRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandShowSam3dReference)
                {
                    parsed.Sam3dJobId =
                        ((string)request["jobId"] ?? "").Trim();
                    parsed.Sam3dRevision =
                        ((string)request["expectedRevision"] ?? "").Trim();
                    parsed.Sam3dSolutionSha256 =
                        ((string)request["solutionSha256"] ?? "").Trim();
                    parsed.TargetUid =
                        ((string)request["targetUid"] ?? "").Trim();
                    parsed.Sam3dKeepReference = true;
                    ParseSam3dReferenceFields(request, parsed);
                    parsed.RescanRequired = false;

                    string validationError =
                        ValidateSam3dShowReferenceRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else if (command == CommandRemoveSam3dReference)
                {
                    parsed.Sam3dJobId =
                        ((string)request["jobId"] ?? "").Trim();
                    parsed.Sam3dExpectedJobRevision =
                        ((string)request["expectedJobRevision"] ?? "").Trim();
                    parsed.RescanRequired = false;

                    string validationError =
                        ValidateSam3dRemoveReferenceRequest(parsed);
                    if (validationError.Length != 0)
                    {
                        RejectRequest(requestId, validationError);
                        return;
                    }
                }
                else
                {
                    RejectRequest(
                        requestId,
                        "Unsupported command. Accepted commands are 'rescan' " +
                        "'applyPersonPreset', 'addPerson', 'addAtom', " +
                        "'applyAtomPreset', 'loadSubscene', " +
                        "'loadCustomUnityAsset', " +
                        "'selectCustomUnityAssetChoice', " +
                        "'setPersonClothingResource', 'setPersonHairItem', " +
                        "'setPersonBodyProportions', " +
                        "'undoPersonBodyProportions', " +
                        "'selectPerson', 'selectAtom', 'loadScene', " +
                        "'controlTimeline', 'applySam3dResult', " +
                        "'undoSam3dResult', 'captureSam3dResult', " +
                        "'showSam3dReference', and 'removeSam3dReference'.");
                    return;
                }

                if (_pendingRequest != null)
                {
                    if (requestId == _pendingRequest.RequestId)
                    {
                        return;
                    }

                    // Repeated package switches can safely collapse pending
                    // rescan-only requests. Never collapse an atom or resource
                    // action: each one names a distinct target or resource.
                    if (_pendingRequest.Command == CommandRescan &&
                        parsed.Command == CommandRescan)
                    {
                        _pendingRequest = parsed;
                        PublishStatus(
                            StateQueued,
                            requestId,
                            "",
                            "",
                            "",
                            "Rescan request queued; an older pending rescan was coalesced.");
                        return;
                    }

                    _skipPendingProcessing = true;
                    RejectRequest(
                        requestId,
                        "Bridge is busy with request " +
                        _pendingRequest.RequestId +
                        ". Submit this request again after it completes.");
                    return;
                }

                _pendingRequest = parsed;
                PublishStatus(
                    StateQueued,
                    requestId,
                    "",
                    "",
                    "",
                    "Request queued.");
            }
            catch (Exception exception)
            {
                RejectRequest(
                    requestId,
                    "Could not parse request: " + DescribeException(exception));
            }
        }

        private static string ValidateApplyRequest(BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            string requiredPrefix = GetPresetPrefix(request.PresetKind);
            if (requiredPrefix.Length == 0)
            {
                return "Unsupported presetKind.";
            }
            return ValidateResourceRef(
                request.ResourceRef,
                requiredPrefix,
                ".vap",
                true,
                "presets of this kind");
        }

        private static string ValidateSceneRequest(BridgeRequest request)
        {
            return ValidateResourceRef(
                request.ResourceRef,
                "Saves/scene/",
                ".json",
                false,
                "scenes");
        }

        private static string ValidateAddAtomRequest(BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            return ValidateAtomType(request.AtomType);
        }

        private static string ValidateAtomPresetRequest(BridgeRequest request)
        {
            string addError = ValidateAddAtomRequest(request);
            if (addError.Length != 0)
            {
                return addError;
            }
            if (request.CreateIfMissing && request.Merge)
            {
                return "createIfMissing and merge cannot both be true.";
            }
            return ValidateResourceRef(
                request.ResourceRef,
                "Custom/Atom/" + request.AtomType + "/",
                ".vap",
                true,
                "presets for atom type " + request.AtomType);
        }

        private static string ValidateSubsceneRequest(BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            return ValidateResourceRef(
                request.ResourceRef,
                "Custom/SubScene/",
                ".json",
                false,
                "SubScenes");
        }

        private static string ValidateCustomUnityAssetRequest(
            BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            string extension = "";
            if (request.ResourceRef != null &&
                request.ResourceRef.EndsWith(
                    ".assetbundle",
                    StringComparison.OrdinalIgnoreCase))
            {
                extension = ".assetbundle";
            }
            else if (request.ResourceRef != null &&
                     request.ResourceRef.EndsWith(
                         ".scene",
                         StringComparison.OrdinalIgnoreCase))
            {
                extension = ".scene";
            }
            if (extension.Length == 0)
            {
                return "resourceRef must name a .assetbundle or .scene resource.";
            }
            return ValidateResourceRef(
                request.ResourceRef,
                "Custom/Assets/",
                extension,
                false,
                "Custom Unity Assets");
        }

        private static string ValidateCustomUnityAssetChoiceRequest(
            BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            if (request.ChoiceIndex <= 0)
            {
                return "choiceIndex must be a positive chooser index.";
            }
            if (!IsHexToken(request.ChoiceToken))
            {
                return "choiceToken must contain exactly 32 hexadecimal characters.";
            }
            return "";
        }

        private static string ValidatePersonClothingRequest(
            BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            if (!IsHexToken(request.ClothingRevision))
            {
                return "revision must contain exactly 32 hexadecimal characters.";
            }

            string resourceRef = request.ResourceRef ?? "";
            string prefix = GetClothingResourcePrefix(resourceRef);
            if (prefix.Length == 0)
            {
                return "Clothing resources must be below " +
                    "Custom/Clothing/Female/ or Custom/Clothing/Male/.";
            }
            return ValidateResourceRef(
                resourceRef,
                prefix,
                ".vam",
                false,
                "clothing items");
        }

        private static string ValidatePersonHairRequest(
            BridgeRequest request)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            if (!IsHexToken(request.HairRevision))
            {
                return "revision must contain exactly 32 hexadecimal characters.";
            }
            if (!IsHexToken(request.HairActionToken))
            {
                return "actionToken must contain exactly 32 hexadecimal characters.";
            }
            return "";
        }

        private static string ValidateBodyProportionRequest(
            BridgeRequest request,
            bool undo)
        {
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            if (!IsHexToken(request.BodyProportionRevision))
            {
                return
                    "expectedRevision must contain exactly 32 hexadecimal characters.";
            }
            if (undo)
            {
                return "";
            }
            if (request.BodyProportionChanges == null ||
                request.BodyProportionChanges.Count == 0 ||
                request.BodyProportionChanges.Count >
                    MaximumBodyProportionChanges)
            {
                return "A bounded body-proportion change list is required.";
            }
            HashSet<string> keys =
                new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            int index;
            for (index = 0;
                 index < request.BodyProportionChanges.Count;
                 index++)
            {
                BodyProportionChange change =
                    request.BodyProportionChanges[index];
                if (change == null || !IsHexToken(change.Key))
                {
                    return
                        "Each body-proportion key must contain exactly 32 hexadecimal characters.";
                }
                if (!keys.Add(change.Key))
                {
                    return "Body-proportion keys must be unique.";
                }
                if (!IsFinite(change.Value) ||
                    Mathf.Abs(change.Value) >
                        MaximumBodyProportionMagnitude)
                {
                    return
                        "Body-proportion values must be finite and between -1 and 1.";
                }
            }
            return "";
        }

        private static string GetClothingResourcePrefix(string resourceRef)
        {
            if (resourceRef == null)
            {
                return "";
            }
            int packageSeparator =
                resourceRef.IndexOf(":/", StringComparison.Ordinal);
            string member =
                packageSeparator >= 0
                ? resourceRef.Substring(packageSeparator + 2)
                : resourceRef;
            if (member.StartsWith(
                    "Custom/Clothing/Female/",
                    StringComparison.OrdinalIgnoreCase))
            {
                return "Custom/Clothing/Female/";
            }
            if (member.StartsWith(
                    "Custom/Clothing/Male/",
                    StringComparison.OrdinalIgnoreCase))
            {
                return "Custom/Clothing/Male/";
            }
            return "";
        }

        private static bool IsHexToken(string value)
        {
            if (value == null || value.Length != 32)
            {
                return false;
            }
            int index;
            for (index = 0; index < value.Length; index++)
            {
                char character = value[index];
                bool digit = character >= '0' && character <= '9';
                bool lower = character >= 'a' && character <= 'f';
                bool upper = character >= 'A' && character <= 'F';
                if (!digit && !lower && !upper)
                {
                    return false;
                }
            }
            return true;
        }

        private static bool IsSha256Token(string value)
        {
            if (value == null || value.Length != 64)
            {
                return false;
            }
            int index;
            for (index = 0; index < value.Length; index++)
            {
                char character = value[index];
                bool digit = character >= '0' && character <= '9';
                bool lower = character >= 'a' && character <= 'f';
                bool upper = character >= 'A' && character <= 'F';
                if (!digit && !lower && !upper)
                {
                    return false;
                }
            }
            return true;
        }

        private static string TimelineItemField(string operation)
        {
            if (operation == "selectClip" || operation == "playClip")
            {
                return "clipId";
            }
            if (operation == "selectSegment")
            {
                return "segmentId";
            }
            if (operation == "selectLayer")
            {
                return "layerId";
            }
            return "";
        }

        private static bool IsTimelineOperation(string operation)
        {
            return
                operation == "play" ||
                operation == "pause" ||
                operation == "stop" ||
                operation == "reset" ||
                operation == "nextFrame" ||
                operation == "previousFrame" ||
                operation == "selectClip" ||
                operation == "playClip" ||
                operation == "selectSegment" ||
                operation == "selectLayer" ||
                operation == "setTime" ||
                operation == "setSpeed" ||
                operation == "setWeight" ||
                operation == "setLocked";
        }

        private static string ValidateTimelineRequest(
            BridgeRequest request)
        {
            if (!IsHexToken(request.TimelineId))
            {
                return "timelineId must contain exactly 32 hexadecimal characters.";
            }
            if (!IsHexToken(request.TimelineRevision))
            {
                return "expectedRevision must contain exactly 32 hexadecimal characters.";
            }
            if (!IsTimelineOperation(request.TimelineOperation))
            {
                return "operation is not an allowlisted Timeline control.";
            }
            if (TimelineItemField(request.TimelineOperation).Length != 0 &&
                !IsHexToken(request.TimelineItemToken))
            {
                return "Timeline item ID must contain exactly 32 hexadecimal characters.";
            }
            if ((request.TimelineOperation == "setTime" ||
                 request.TimelineOperation == "setSpeed" ||
                 request.TimelineOperation == "setWeight" ||
                 request.TimelineOperation == "setLocked") &&
                !request.HasTimelineValue)
            {
                return "Timeline setter operation requires value.";
            }
            float value = request.TimelineNumberValue;
            if (request.TimelineOperation == "setTime" &&
                (!IsFinite(value) || value < 0f || value > 86400f))
            {
                return "setTime value must be between 0 and 86400.";
            }
            if (request.TimelineOperation == "setSpeed" &&
                (!IsFinite(value) || value < -1f || value > 5f))
            {
                return "setSpeed value must be between -1 and 5.";
            }
            if (request.TimelineOperation == "setWeight" &&
                (!IsFinite(value) || value < 0f || value > 1f))
            {
                return "setWeight value must be between 0 and 1.";
            }
            return "";
        }

        private static bool IsFinite(float value)
        {
            return !float.IsNaN(value) && !float.IsInfinity(value);
        }

        private static string ValidateSam3dIdentity(
            BridgeRequest request)
        {
            if (!IsHexToken(request.Sam3dJobId))
            {
                return "jobId must contain exactly 32 hexadecimal characters.";
            }
            if (!IsHexToken(request.Sam3dRevision))
            {
                return "expectedRevision must contain exactly 32 hexadecimal characters.";
            }
            return "";
        }

        private static void ParseSam3dReferenceFields(
            JSONClass document,
            BridgeRequest request)
        {
            request.Sam3dExpectedJobRevision =
                ((string)document["expectedJobRevision"] ?? "").Trim();
            request.Sam3dReferenceResourceRef =
                ((string)document["referenceResourceRef"] ?? "").Trim();
            request.Sam3dReferenceSha256 =
                ((string)document["referenceSha256"] ?? "").Trim();
            request.Sam3dReferenceWidth =
                document["referenceWidth"].AsInt;
            request.Sam3dReferenceHeight =
                document["referenceHeight"].AsInt;
        }

        private static string ValidateSam3dReferenceMetadata(
            BridgeRequest request)
        {
            if (!IsHexToken(request.Sam3dExpectedJobRevision))
            {
                return
                    "expectedJobRevision must contain exactly 32 hexadecimal characters.";
            }
            if (!IsSha256Token(request.Sam3dReferenceSha256))
            {
                return
                    "referenceSha256 must contain exactly 64 hexadecimal characters.";
            }
            if (request.Sam3dReferenceWidth < 1 ||
                request.Sam3dReferenceWidth >
                    Sam3dReferenceMaximumDimension ||
                request.Sam3dReferenceHeight < 1 ||
                request.Sam3dReferenceHeight >
                    Sam3dReferenceMaximumDimension ||
                (long)request.Sam3dReferenceWidth *
                    (long)request.Sam3dReferenceHeight >
                    50000000L)
            {
                return
                    "referenceWidth and referenceHeight exceed the bounded image limits.";
            }
            string resource =
                request.Sam3dReferenceResourceRef ?? "";
            if (resource.Length == 0 ||
                resource.Length > MaximumResourceRefLength ||
                resource.IndexOf('\\') >= 0 ||
                ContainsControlCharacter(resource) ||
                !resource.StartsWith(
                    Sam3dReferencePrefix,
                    StringComparison.Ordinal))
            {
                return
                    "referenceResourceRef must be an owned VAM-PIP SAM3D image path.";
            }
            string basename =
                resource.Substring(Sam3dReferencePrefix.Length);
            string expected =
                (request.Sam3dJobId ?? "").ToLowerInvariant();
            if (
                !string.Equals(
                    basename,
                    expected + ".jpg",
                    StringComparison.Ordinal) &&
                !string.Equals(
                    basename,
                    expected + ".jpeg",
                    StringComparison.Ordinal) &&
                !string.Equals(
                    basename,
                    expected + ".png",
                    StringComparison.Ordinal))
            {
                return
                    "referenceResourceRef must be named for the exact SAM3D job.";
            }
            return "";
        }

        private static string ValidateSam3dApplyRequest(
            BridgeRequest request)
        {
            string identityError = ValidateSam3dIdentity(request);
            if (identityError.Length != 0)
            {
                return identityError;
            }
            if (!IsSha256Token(request.Sam3dSolutionSha256))
            {
                return
                    "solutionSha256 must contain exactly 64 hexadecimal characters.";
            }
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            string cameraError =
                ValidateTargetUid(request.Sam3dCameraUid);
            if (cameraError.Length != 0)
            {
                return "cameraUid " + cameraError;
            }
            if (request.Sam3dKeepReference)
            {
                return ValidateSam3dReferenceMetadata(request);
            }
            return "";
        }

        private static string ValidateSam3dShowReferenceRequest(
            BridgeRequest request)
        {
            string identityError = ValidateSam3dIdentity(request);
            if (identityError.Length != 0)
            {
                return identityError;
            }
            if (!IsSha256Token(request.Sam3dSolutionSha256))
            {
                return
                    "solutionSha256 must contain exactly 64 hexadecimal characters.";
            }
            string targetError = ValidateTargetUid(request.TargetUid);
            if (targetError.Length != 0)
            {
                return targetError;
            }
            return ValidateSam3dReferenceMetadata(request);
        }

        private static string ValidateSam3dRemoveReferenceRequest(
            BridgeRequest request)
        {
            if (!IsHexToken(request.Sam3dJobId))
            {
                return
                    "jobId must contain exactly 32 hexadecimal characters.";
            }
            if (!IsHexToken(request.Sam3dExpectedJobRevision))
            {
                return
                    "expectedJobRevision must contain exactly 32 hexadecimal characters.";
            }
            return "";
        }

        private static string ValidateSam3dCaptureRequest(
            BridgeRequest request)
        {
            string identityError = ValidateSam3dIdentity(request);
            if (identityError.Length != 0)
            {
                return identityError;
            }
            if (!IsSha256Token(request.Sam3dSolutionSha256))
            {
                return
                    "solutionSha256 must contain exactly 64 hexadecimal characters.";
            }
            string cameraError =
                ValidateTargetUid(request.Sam3dCameraUid);
            if (cameraError.Length != 0)
            {
                return "cameraUid " + cameraError;
            }
            return "";
        }

        private static string ValidateTargetUid(string targetUid)
        {
            if (targetUid == null ||
                targetUid.Length == 0 ||
                targetUid.Length > 200)
            {
                return "targetUid must contain 1 to 200 characters.";
            }
            if (ContainsControlCharacter(targetUid))
            {
                return "targetUid must not contain control characters.";
            }
            return "";
        }

        private static string ValidateAtomType(string atomType)
        {
            if (!IsAllowedAtomType(atomType))
            {
                return "atomType is not an allowlisted VaM 1.22 native atom type.";
            }
            return "";
        }

        private static bool IsAllowedAtomType(string atomType)
        {
            return atomType != null &&
                atomType.IndexOf('|') < 0 &&
                AllowedAtomTypes.IndexOf(
                    "|" + atomType + "|",
                    StringComparison.Ordinal) >= 0;
        }

        private static string GetPresetPrefix(string presetKind)
        {
            if (presetKind == "appearance")
                return "Custom/Atom/Person/Appearance/";
            if (presetKind == "animation")
                return "Custom/Atom/Person/AnimationPresets/";
            if (presetKind == "breastPhysics")
                return "Custom/Atom/Person/BreastPhysics/";
            if (presetKind == "clothing")
                return "Custom/Atom/Person/Clothing/";
            if (presetKind == "general")
                return "Custom/Atom/Person/General/";
            if (presetKind == "glutePhysics")
                return "Custom/Atom/Person/GlutePhysics/";
            if (presetKind == "hair")
                return "Custom/Atom/Person/Hair/";
            if (presetKind == "morphs")
                return "Custom/Atom/Person/Morphs/";
            if (presetKind == "plugins")
                return "Custom/Atom/Person/Plugins/";
            if (presetKind == "pose")
                return "Custom/Atom/Person/Pose/";
            if (presetKind == "skin")
                return "Custom/Atom/Person/Skin/";
            return "";
        }

        private static string GetPresetStorableId(string presetKind)
        {
            if (presetKind == "appearance") return "AppearancePresets";
            if (presetKind == "animation") return "AnimationPresets";
            if (presetKind == "breastPhysics")
                return "FemaleBreastPhysicsPresets";
            if (presetKind == "clothing") return "ClothingPresets";
            if (presetKind == "general") return "Preset";
            if (presetKind == "glutePhysics")
                return "FemaleGlutePhysicsPresets";
            if (presetKind == "hair") return "HairPresets";
            if (presetKind == "morphs") return "MorphPresets";
            if (presetKind == "plugins") return "PluginPresets";
            if (presetKind == "pose") return "PosePresets";
            if (presetKind == "skin") return "SkinPresets";
            return "";
        }

        private static string ValidateResourceRef(
            string resourceRef,
            string requiredPrefix,
            string extension,
            bool requirePresetBasename,
            string resourceDescription)
        {
            if (resourceRef == null ||
                resourceRef.Length == 0 ||
                resourceRef.Length > MaximumResourceRefLength)
            {
                return "resourceRef must contain 1 to " +
                    MaximumResourceRefLength +
                    " characters.";
            }
            if (resourceRef != resourceRef.Trim())
            {
                return "resourceRef must not have leading or trailing whitespace.";
            }
            if (resourceRef[0] == '/' ||
                resourceRef.IndexOf('\\') >= 0 ||
                resourceRef.IndexOf("://", StringComparison.Ordinal) >= 0)
            {
                return "resourceRef must be a relative VaM resource reference.";
            }
            if (ContainsControlCharacter(resourceRef))
            {
                return "resourceRef must not contain control characters.";
            }
            if (!resourceRef.EndsWith(
                extension,
                StringComparison.OrdinalIgnoreCase))
            {
                return "resourceRef must name a " + extension + " resource.";
            }
            if (requirePresetBasename)
            {
                int lastSlash = resourceRef.LastIndexOf('/');
                string basename = resourceRef.Substring(lastSlash + 1);
                if (!basename.StartsWith(
                    "Preset_",
                    StringComparison.OrdinalIgnoreCase))
                {
                    return "resourceRef basename must begin with Preset_.";
                }
            }

            string[] pathSegments = resourceRef.Split('/');
            int pathIndex;
            for (pathIndex = 0; pathIndex < pathSegments.Length; pathIndex++)
            {
                if (pathSegments[pathIndex].Length == 0 ||
                    pathSegments[pathIndex] == "." ||
                    pathSegments[pathIndex] == "..")
                {
                    return "resourceRef must not contain empty, '.' or '..' " +
                        "path segments.";
                }
            }

            int packageSeparator =
                resourceRef.IndexOf(":/", StringComparison.Ordinal);
            if (packageSeparator < 0)
            {
                if (resourceRef.IndexOf(':') >= 0 ||
                    !resourceRef.StartsWith(
                        requiredPrefix,
                        StringComparison.OrdinalIgnoreCase))
                {
                    return "Local " + resourceDescription + " must be below " +
                        requiredPrefix +
                        ".";
                }
                return "";
            }

            string packageRef = resourceRef.Substring(0, packageSeparator);
            string packageMember = resourceRef.Substring(packageSeparator + 2);
            if (packageRef.IndexOf(':') >= 0 ||
                packageRef.IndexOf('/') >= 0 ||
                packageMember.IndexOf(':') >= 0 ||
                resourceRef.IndexOf(
                    ":/",
                    packageSeparator + 2,
                    StringComparison.Ordinal) >= 0 ||
                !packageMember.StartsWith(
                    requiredPrefix,
                    StringComparison.OrdinalIgnoreCase))
            {
                return "Packaged " + resourceDescription + " must use " +
                    "creator.package.version:/" +
                    requiredPrefix +
                    "*" +
                    extension +
                    ".";
            }

            string[] packageParts = packageRef.Split('.');
            if (packageParts.Length < 3)
            {
                return "Packaged resourceRef must include creator, package, and version.";
            }
            for (pathIndex = 0; pathIndex < packageParts.Length; pathIndex++)
            {
                if (packageParts[pathIndex].Length == 0)
                {
                    return "Packaged resourceRef has an empty identity component.";
                }
            }
            return "";
        }

        private static bool ContainsControlCharacter(string value)
        {
            int index;
            for (index = 0; index < value.Length; index++)
            {
                if (value[index] < ' ' || value[index] == '\u007f')
                {
                    return true;
                }
            }
            return false;
        }

        private void RejectRequest(string requestId, string message)
        {
            if (_pendingRequest != null &&
                requestId != _pendingRequest.RequestId)
            {
                _skipPendingProcessing = true;
                _mailboxRejectedRequestId = requestId ?? "";
                _mailboxRejectedMessage = message ?? "";
            }
            PublishStatus(StateError, requestId, "", UtcNow(), "", message);
            SuperController.LogError("[VAM-PIP Bridge] " + message);
        }

        private void RestoreMailboxRejectionStatus()
        {
            if (_mailboxRejectedMessage.Length == 0)
            {
                return;
            }
            PublishStatus(
                StateError,
                _mailboxRejectedRequestId,
                "",
                UtcNow(),
                "",
                _mailboxRejectedMessage);
        }

        private void ProcessPendingRequest(float now)
        {
            if (_pendingRequest == null || _requestInProgress)
            {
                return;
            }

            string requestId = _pendingRequest.RequestId;
            if (SuperController.singleton == null)
            {
                PublishStatus(
                    StateQueued,
                    requestId,
                    "",
                    "",
                    "",
                    "Waiting for VaM to finish initializing.");
                return;
            }
            if (SuperController.singleton.isLoading)
            {
                PublishStatus(
                    StateDeferredLoading,
                    requestId,
                    "",
                    "",
                    "",
                    "Waiting for scene loading to finish.");
                return;
            }
            if (_pendingRequest.RescanRequired && now < _nextAllowedRescanAt)
            {
                PublishStatus(
                    StateQueued,
                    requestId,
                    "",
                    "",
                    "",
                    "Request queued by the rescan rate limiter.");
                return;
            }

            BridgeRequest request = _pendingRequest;
            if (request.Command == CommandAddPerson ||
                request.Command == CommandAddAtom)
            {
                _requestInProgress = true;
                try
                {
                    StartCoroutine(
                        ExecuteAddAtom(
                            request,
                            request.Command == CommandAddPerson
                            ? "Person"
                            : request.AtomType));
                }
                catch (Exception exception)
                {
                    _requestInProgress = false;
                    _pendingRequest = null;
                    FailRequest(
                        request,
                        "",
                        "Could not start atom creation: " +
                        DescribeException(exception));
                }
                return;
            }
            if (request.Command == CommandApplyAtomPreset ||
                request.Command == CommandLoadSubscene ||
                request.Command == CommandLoadCustomUnityAsset ||
                request.Command == CommandSelectCustomUnityAssetChoice)
            {
                _requestInProgress = true;
                try
                {
                    if (request.Command == CommandApplyAtomPreset)
                    {
                        StartCoroutine(ExecuteApplyAtomPreset(request));
                    }
                    else if (request.Command == CommandLoadSubscene)
                    {
                        StartCoroutine(ExecuteLoadSubscene(request));
                    }
                    else if (request.Command == CommandLoadCustomUnityAsset)
                    {
                        StartCoroutine(ExecuteLoadCustomUnityAsset(request));
                    }
                    else
                    {
                        StartCoroutine(
                            ExecuteSelectCustomUnityAssetChoice(request));
                    }
                }
                catch (Exception exception)
                {
                    _requestInProgress = false;
                    _pendingRequest = null;
                    FailRequest(
                        request,
                        "",
                        "Could not start atom resource action: " +
                        DescribeException(exception));
                }
                return;
            }
            if (request.Command == CommandLoadScene)
            {
                _requestInProgress = true;
                try
                {
                    StartCoroutine(ExecuteLoadScene(request));
                }
                catch (Exception exception)
                {
                    _requestInProgress = false;
                    _pendingRequest = null;
                    FailRequest(
                        request,
                        "",
                        "Could not start scene loading: " +
                        DescribeException(exception));
                }
                return;
            }
            if (request.Command == CommandApplySam3dResult ||
                request.Command == CommandUndoSam3dResult ||
                request.Command == CommandCaptureSam3dResult ||
                request.Command == CommandShowSam3dReference ||
                request.Command == CommandRemoveSam3dReference)
            {
                _requestInProgress = true;
                try
                {
                    StartCoroutine(
                        request.Command == CommandApplySam3dResult
                        ? ExecuteApplySam3dResult(request)
                        : request.Command == CommandUndoSam3dResult
                        ? ExecuteUndoSam3dResult(request)
                        : request.Command == CommandCaptureSam3dResult
                        ? ExecuteCaptureSam3dResult(request)
                        : request.Command == CommandShowSam3dReference
                        ? ExecuteShowSam3dReference(request)
                        : ExecuteRemoveSam3dReference(request));
                }
                catch (Exception exception)
                {
                    _requestInProgress = false;
                    _pendingRequest = null;
                    FailRequest(
                        request,
                        "",
                        "Could not start the SAM3D action: " +
                        DescribeException(exception));
                }
                return;
            }

            _pendingRequest = null;
            if (request.Command == CommandRescan)
            {
                ExecuteRescan(request);
            }
            else if (request.Command == CommandApplyPersonPreset)
            {
                ExecuteApplyPersonPreset(request);
            }
            else if (request.Command == CommandSetPersonClothingResource)
            {
                ExecuteSetPersonClothingResource(request);
            }
            else if (request.Command == CommandSetPersonHairItem)
            {
                ExecuteSetPersonHairItem(request);
            }
            else if (
                request.Command == CommandSetPersonBodyProportions ||
                request.Command == CommandUndoPersonBodyProportions)
            {
                ExecutePersonBodyProportions(
                    request,
                    request.Command ==
                        CommandUndoPersonBodyProportions);
            }
            else if (request.Command == CommandControlTimeline)
            {
                ExecuteTimelineControl(request);
            }
            else
            {
                ExecuteSelectAtom(
                    request,
                    request.Command == CommandSelectPerson);
            }
        }

        private void ExecuteRescan(BridgeRequest request)
        {
            string startedAt = UtcNow();
            string backend = "";
            PublishStatus(
                StateRescanning,
                request.RequestId,
                startedAt,
                "",
                "",
                "Rescanning VaM packages.");

            try
            {
                SuperController.singleton.RescanPackages();
                backend = "vam";
                string message =
                    request.BrowserAssistMode == "off"
                    ? "Core VaM package rescan completed."
                    : "Core VaM package rescan completed. Reload BrowserAssist " +
                      "if it must see newly enabled packages.";
                CompleteRequest(request.RequestId);
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    backend,
                    message);
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Request " +
                    request.RequestId +
                    " completed using vam.");
            }
            catch (Exception exception)
            {
                _lastHandledRequestId = request.RequestId;
                string message =
                    "Package rescan failed: " + DescribeException(exception);
                PublishStatus(
                    StateError,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    backend,
                    message);
                SuperController.LogError("[VAM-PIP Bridge] " + message);
            }
            finally
            {
                _nextAllowedRescanAt =
                    Time.realtimeSinceStartup + MinimumRescanIntervalSeconds;
            }
        }

        private void ExecuteApplyPersonPreset(BridgeRequest request)
        {
            string startedAt = UtcNow();
            string backend = "";
            bool rescanAttempted = false;

            try
            {
                if (request.RescanRequired)
                {
                    rescanAttempted = true;
                    PublishStatus(
                        StateRescanning,
                        request.RequestId,
                        startedAt,
                        "",
                        "",
                        "Rescanning VaM packages before applying the Person preset.");
                    SuperController.singleton.RescanPackages();
                    backend = "vam";
                }

                PublishStatus(
                    StateApplying,
                    request.RequestId,
                    startedAt,
                    "",
                    backend,
                    "Applying Person " + request.PresetKind + " preset.");

                if (!FileManagerSecure.FileExists(request.ResourceRef))
                {
                    throw new Exception(
                        "The validated preset does not exist or is not visible to VaM.");
                }

                Atom person =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (person == null || person.type != "Person")
                {
                    throw new Exception(
                        "targetUid does not identify a Person atom in the current scene.");
                }

                string storableId =
                    GetPresetStorableId(request.PresetKind);
                JSONStorable presetStorable =
                    person.GetStorableByID(storableId);
                if (presetStorable == null)
                {
                    throw new Exception(
                        "The target Person does not expose " +
                        storableId +
                        ".");
                }
                JSONStorableUrl presetBrowsePath =
                    presetStorable.GetUrlJSONParam("presetBrowsePath");
                if (presetBrowsePath == null)
                {
                    throw new Exception(
                        "The target Person preset storable has no presetBrowsePath.");
                }

                JSONStorableBool loadPresetOnSelect =
                    presetStorable.GetBoolJSONParam("loadPresetOnSelect");
                bool previousLoadPresetOnSelect = false;
                if (loadPresetOnSelect != null)
                {
                    previousLoadPresetOnSelect = loadPresetOnSelect.val;
                    loadPresetOnSelect.val = false;
                }
                try
                {
                    presetBrowsePath.val =
                        SuperController.singleton.NormalizePath(
                            request.ResourceRef);
                    presetStorable.CallAction(
                        request.Merge
                        ? "MergeLoadPreset"
                        : "LoadPreset");
                }
                finally
                {
                    if (loadPresetOnSelect != null)
                    {
                        loadPresetOnSelect.val = previousLoadPresetOnSelect;
                    }
                }
                backend = "vam";
                CompleteRequest(request.RequestId);
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    backend,
                    "Person " +
                    request.PresetKind +
                    (request.Merge ? " preset merged." : " preset applied."));
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Applied " +
                    request.PresetKind +
                    " preset to " +
                    request.TargetUid +
                    ".");
            }
            catch (Exception exception)
            {
                _lastHandledRequestId = request.RequestId;
                string message =
                    "Person preset request failed: " +
                    DescribeException(exception);
                PublishStatus(
                    StateError,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    backend,
                    message);
                SuperController.LogError("[VAM-PIP Bridge] " + message);
            }
            finally
            {
                if (rescanAttempted)
                {
                    _nextAllowedRescanAt =
                        Time.realtimeSinceStartup +
                        MinimumRescanIntervalSeconds;
                }
            }
        }

        private void ExecuteSetPersonClothingResource(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            string backend = "";
            bool rescanAttempted = false;
            try
            {
                if (request.RescanRequired)
                {
                    rescanAttempted = true;
                    PublishStatus(
                        StateRescanning,
                        request.RequestId,
                        startedAt,
                        "",
                        "",
                        "Rescanning VaM packages before changing clothing.");
                    SuperController.singleton.RescanPackages();
                    backend = "vam";
                }

                PublishStatus(
                    StateApplying,
                    request.RequestId,
                    startedAt,
                    "",
                    backend,
                    request.ClothingActive
                    ? "Putting on an individual clothing item."
                    : "Removing an individual clothing item.");

                if (request.ClothingActive &&
                    !FileManagerSecure.FileExists(request.ResourceRef))
                {
                    throw new Exception(
                        "The validated clothing item does not exist or is not " +
                        "visible to VaM.");
                }

                Atom person =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (person == null || person.type != "Person")
                {
                    throw new Exception(
                        "targetUid does not identify a Person atom in the " +
                        "current scene.");
                }
                DAZCharacterSelector geometry =
                    person.GetStorableByID("geometry")
                    as DAZCharacterSelector;
                if (geometry == null)
                {
                    throw new Exception(
                        "The target Person does not expose native geometry.");
                }

                PersonClothingSnapshot snapshot = null;
                if (!_personClothingSnapshots.TryGetValue(
                        request.TargetUid,
                        out snapshot) ||
                    !object.ReferenceEquals(snapshot.Atom, person) ||
                    !object.ReferenceEquals(snapshot.Geometry, geometry) ||
                    !string.Equals(
                        snapshot.Revision,
                        request.ClothingRevision,
                        StringComparison.OrdinalIgnoreCase))
                {
                    throw new Exception(
                        "The Person clothing revision is stale; refresh the " +
                        "live roster.");
                }
                List<ActiveClothingEntry> entries =
                    GetActiveClothingEntries(person, geometry);
                string currentGeneration =
                    BuildPersonClothingGenerationKey(geometry, entries);
                if (!string.Equals(
                        snapshot.GenerationKey,
                        currentGeneration,
                        StringComparison.Ordinal))
                {
                    throw new Exception(
                        "The Person's clothing or gender changed; refresh the " +
                        "live roster.");
                }

                string prefix =
                    GetClothingResourcePrefix(request.ResourceRef);
                string gender = geometry.gender.ToString();
                bool genderCompatible =
                    prefix == "Custom/Clothing/Female/"
                    ? gender.Equals(
                        "Female",
                        StringComparison.OrdinalIgnoreCase) ||
                      gender.Equals(
                        "Both",
                        StringComparison.OrdinalIgnoreCase)
                    : gender.Equals(
                        "Male",
                        StringComparison.OrdinalIgnoreCase) ||
                      gender.Equals(
                        "Both",
                        StringComparison.OrdinalIgnoreCase);
                if (request.ClothingActive && !genderCompatible)
                {
                    throw new Exception(
                        "The clothing item is incompatible with the Person's " +
                        "current gender.");
                }

                string normalized =
                    FileManagerSecure.NormalizePath(request.ResourceRef);
                DAZClothingItem resolvedItem =
                    geometry.GetClothingItem(normalized);
                bool locked =
                    resolvedItem != null && resolvedItem.locked;
                bool observedWorn = false;
                int entryIndex;
                for (entryIndex = 0;
                     entryIndex < entries.Count;
                     entryIndex++)
                {
                    ActiveClothingEntry entry = entries[entryIndex];
                    if (entry.ResourceRef.Length != 0 &&
                        entry.ResourceRef.Equals(
                            normalized,
                            StringComparison.OrdinalIgnoreCase))
                    {
                        observedWorn = true;
                        if (entry.Locked)
                        {
                            locked = true;
                        }
                    }
                }
                JSONStorableBool active =
                    geometry.GetBoolJSONParam("clothing:" + normalized);
                bool alreadyRemoved =
                    active == null &&
                    !request.ClothingActive &&
                    !observedWorn;
                if (active == null && !alreadyRemoved)
                {
                    throw new Exception(
                        "VaM did not register the exact clothing item on this " +
                        "Person after the package rescan.");
                }
                if (!alreadyRemoved &&
                    active.val != request.ClothingActive &&
                    locked)
                {
                    throw new Exception(
                        "The clothing item is locked in VaM; unlock it before " +
                        "changing it externally.");
                }

                if (!alreadyRemoved)
                {
                    active.val = request.ClothingActive;
                    if (active.val != request.ClothingActive)
                    {
                        throw new Exception(
                            "VaM refused the requested clothing state.");
                    }
                }

                backend = "vam";
                CompleteRequest(request.RequestId);
                PublishSceneStatus();
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    backend,
                    request.ClothingActive
                    ? "Clothing item is worn."
                    : alreadyRemoved
                      ? "Clothing item was already removed."
                      : "Clothing item was removed.");
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Clothing state changed for " +
                    request.TargetUid +
                    ".");
            }
            catch (Exception exception)
            {
                FailRequest(
                    request,
                    startedAt,
                    "Person clothing request failed: " +
                    DescribeException(exception));
            }
            finally
            {
                if (rescanAttempted)
                {
                    _nextAllowedRescanAt =
                        Time.realtimeSinceStartup +
                        MinimumRescanIntervalSeconds;
                }
            }
        }

        private void ExecuteSetPersonHairItem(BridgeRequest request)
        {
            string startedAt = UtcNow();
            try
            {
                PublishStatus(
                    StateApplying,
                    request.RequestId,
                    startedAt,
                    "",
                    "",
                    "Removing one active Hair layer.");

                Atom person =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (person == null || person.type != "Person")
                {
                    throw new Exception(
                        "targetUid does not identify a Person atom in the " +
                        "current scene.");
                }
                DAZCharacterSelector geometry =
                    person.GetStorableByID("geometry")
                    as DAZCharacterSelector;
                if (geometry == null)
                {
                    throw new Exception(
                        "The target Person does not expose native geometry.");
                }

                PersonHairSnapshot snapshot = null;
                if (!_personHairSnapshots.TryGetValue(
                        request.TargetUid,
                        out snapshot) ||
                    !object.ReferenceEquals(snapshot.Atom, person) ||
                    !object.ReferenceEquals(snapshot.Geometry, geometry) ||
                    !string.Equals(
                        snapshot.Revision,
                        request.HairRevision,
                        StringComparison.OrdinalIgnoreCase))
                {
                    throw new Exception(
                        "The Person Hair revision is stale; refresh the live " +
                        "roster.");
                }

                List<ActiveHairEntry> entries =
                    GetActiveHairEntries(person, geometry);
                string currentGeneration =
                    BuildPersonHairGenerationKey(geometry, entries);
                if (!string.Equals(
                        snapshot.GenerationKey,
                        currentGeneration,
                        StringComparison.Ordinal) ||
                    snapshot.Items == null ||
                    snapshot.ActionTokens == null ||
                    snapshot.Items.Count != entries.Count ||
                    snapshot.ActionTokens.Count != entries.Count ||
                    snapshot.PublishedCount < 0 ||
                    snapshot.PublishedCount > entries.Count)
                {
                    throw new Exception(
                        "The Person's Hair changed; refresh the live roster.");
                }

                ActiveHairEntry selected = null;
                int selectedIndex = -1;
                int tokenMatches = 0;
                int entryIndex;
                for (entryIndex = 0;
                     entryIndex < entries.Count;
                     entryIndex++)
                {
                    if (!object.ReferenceEquals(
                            snapshot.Items[entryIndex],
                            entries[entryIndex].Item))
                    {
                        throw new Exception(
                            "The Person's Hair identity changed; refresh the " +
                            "live roster.");
                    }
                    if (snapshot.ActionTokens[entryIndex].Equals(
                            request.HairActionToken,
                            StringComparison.OrdinalIgnoreCase))
                    {
                        tokenMatches++;
                        selected = entries[entryIndex];
                        selectedIndex = entryIndex;
                    }
                }
                if (tokenMatches != 1 ||
                    selected == null ||
                    selectedIndex < 0 ||
                    selectedIndex >= snapshot.PublishedCount)
                {
                    throw new Exception(
                        "The Hair action token is stale or ambiguous; refresh " +
                        "the live roster.");
                }
                if (selected.Locked || selected.Item.locked)
                {
                    throw new Exception(
                        "The Hair layer is locked in VaM; unlock it before " +
                        "removing it externally.");
                }
                if (!selected.Item.active)
                {
                    throw new Exception(
                        "The Hair layer is no longer active; refresh the live " +
                        "roster.");
                }

                geometry.SetActiveHairItem(
                    selected.Item,
                    false,
                    false,
                    false);
                if (selected.Item.active)
                {
                    throw new Exception(
                        "VaM refused to disable the selected Hair layer.");
                }

                CompleteRequest(request.RequestId);
                PublishSceneStatus();
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    "vam",
                    "Hair layer was removed.");
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Hair layer removed from " +
                    request.TargetUid +
                    ".");
            }
            catch (Exception exception)
            {
                FailRequest(
                    request,
                    startedAt,
                    "Person Hair request failed: " +
                    DescribeException(exception));
            }
        }

        private static void SetBodyProportionMorphValue(
            DAZMorph morph,
            float value)
        {
            if (morph == null)
            {
                throw new Exception(
                    "A body-proportion morph is no longer available.");
            }
            morph.LoadDeltas();
            morph.SetValueThreadSafe(value);
            morph.SyncJSON();
            if (!IsFinite(morph.morphValue) ||
                Mathf.Abs(morph.morphValue - value) > 0.0001f)
            {
                throw new Exception(
                    "VaM did not accept a body-proportion morph value.");
            }
        }

        private static void RestoreBodyProportionValues(
            List<BodyProportionUndoValue> values)
        {
            if (values == null)
            {
                return;
            }
            int index;
            for (index = values.Count - 1; index >= 0; index--)
            {
                BodyProportionUndoValue saved = values[index];
                if (saved != null && saved.Morph != null)
                {
                    SetBodyProportionMorphValue(
                        saved.Morph,
                        saved.Value);
                }
            }
        }

        private void ExecutePersonBodyProportions(
            BridgeRequest request,
            bool undo)
        {
            string startedAt = UtcNow();
            List<BodyProportionUndoValue> rollback =
                new List<BodyProportionUndoValue>();
            PersonBodyProportionUndo priorUndo = null;
            bool priorUndoPresent = false;
            bool undoBookkeepingChanged = false;
            try
            {
                PublishStatus(
                    StateApplying,
                    request.RequestId,
                    startedAt,
                    "",
                    "",
                    undo
                    ? "Restoring the previous body proportions."
                    : "Applying bounded body-proportion morphs.");

                Atom person =
                    SuperController.singleton.GetAtomByUid(
                        request.TargetUid);
                Atom selected =
                    SuperController.singleton.GetSelectedAtom();
                if (person == null ||
                    person.type != "Person" ||
                    !object.ReferenceEquals(person, selected))
                {
                    throw new Exception(
                        "Body proportions can only be changed on the " +
                        "currently selected Person.");
                }
                if (CurrentSam3dSnapshot() != null)
                {
                    throw new Exception(
                        "Undo the currently applied SAM3D pose before " +
                        "changing body proportions; the two exact undo " +
                        "snapshots cannot overlap.");
                }
                DAZCharacterSelector geometry =
                    person.GetStorableByID("geometry")
                    as DAZCharacterSelector;
                if (geometry == null)
                {
                    throw new Exception(
                        "The selected Person does not expose native geometry.");
                }
                priorUndoPresent =
                    _personBodyProportionUndo.TryGetValue(
                        request.TargetUid,
                        out priorUndo);
                if (!undo && priorUndoPresent)
                {
                    throw new Exception(
                        "This Person already has an exact body-proportion " +
                        "undo. Restore it before applying another fit.");
                }

                List<BodyProportionMorphEntry> currentEntries =
                    GetBodyProportionMorphEntries(geometry);

                if (undo)
                {
                    PersonBodyProportionUndo savedUndo = priorUndo;
                    if (!priorUndoPresent ||
                        !object.ReferenceEquals(savedUndo.Atom, person) ||
                        !object.ReferenceEquals(
                            savedUndo.Geometry,
                            geometry) ||
                        !string.Equals(
                            savedUndo.Revision,
                            request.BodyProportionRevision,
                            StringComparison.OrdinalIgnoreCase) ||
                        !string.Equals(
                            savedUndo.PostApplyMorphStateKey,
                            BuildBodyProportionMorphStateKey(
                                geometry,
                                currentEntries),
                            StringComparison.Ordinal) ||
                        savedUndo.Values == null ||
                        savedUndo.Values.Count == 0)
                    {
                        throw new Exception(
                            "No exact body-proportion undo is available for " +
                            "this revision.");
                    }
                    int undoIndex;
                    for (undoIndex = 0;
                         undoIndex < savedUndo.Values.Count;
                         undoIndex++)
                    {
                        BodyProportionUndoValue saved =
                            savedUndo.Values[undoIndex];
                        if (!ContainsEligibleBodyProportionMorph(
                                currentEntries,
                                saved.Morph))
                        {
                            throw new Exception(
                                "A saved body-proportion morph is no longer " +
                                "eligible; undo was not applied.");
                        }
                        BodyProportionUndoValue rollbackValue =
                            new BodyProportionUndoValue();
                        rollbackValue.Morph = saved.Morph;
                        rollbackValue.Value = saved.Morph.morphValue;
                        rollback.Add(rollbackValue);
                    }
                    RestoreBodyProportionValues(savedUndo.Values);
                    _personBodyProportionUndo.Remove(
                        request.TargetUid);
                    undoBookkeepingChanged = true;
                }
                else
                {
                    PersonBodyProportionSnapshot snapshot = null;
                    if (!_personBodyProportionSnapshots.TryGetValue(
                            request.TargetUid,
                            out snapshot) ||
                        !object.ReferenceEquals(snapshot.Atom, person) ||
                        !object.ReferenceEquals(
                            snapshot.Geometry,
                            geometry) ||
                        !string.Equals(
                            snapshot.Revision,
                            request.BodyProportionRevision,
                            StringComparison.OrdinalIgnoreCase))
                    {
                        throw new Exception(
                            "The body-proportion revision is stale; refresh " +
                            "the selected Person.");
                    }
                    string currentBodyShapeChecksum = "";
                    if (!TryBodyShapeMeshChecksum(
                            geometry,
                            out currentBodyShapeChecksum) ||
                        !string.Equals(
                            snapshot.BodyShapeMeshChecksum,
                            currentBodyShapeChecksum,
                            StringComparison.Ordinal))
                    {
                        throw new Exception(
                            "The neutral body-shape cache changed; refresh " +
                            "the selected Person.");
                    }
                    if (!IsValidBodyShapeSignature(
                            snapshot.BodyShape))
                    {
                        throw new Exception(
                            "The neutral body-shape cache is not ready; wait " +
                            "for preparation or inspect bodyShapeReason.");
                    }
                    string currentGeneration =
                        BuildBodyProportionGenerationKey(
                            geometry,
                            currentEntries,
                            snapshot.BodyShape,
                            currentBodyShapeChecksum);
                    if (!IsCurrentBodyProportionSnapshot(
                            snapshot,
                            currentEntries,
                            currentGeneration))
                    {
                        throw new Exception(
                            "The Person's morph state changed; refresh body " +
                            "proportions before applying.");
                    }

                    PersonBodyProportionUndo newUndo =
                        new PersonBodyProportionUndo();
                    newUndo.Atom = person;
                    newUndo.Geometry = geometry;
                    newUndo.TargetUid = request.TargetUid;
                    newUndo.Revision =
                        Guid.NewGuid().ToString("N");
                    newUndo.Values =
                        new List<BodyProportionUndoValue>();

                    int changeIndex;
                    for (changeIndex = 0;
                         changeIndex <
                            request.BodyProportionChanges.Count;
                         changeIndex++)
                    {
                        BodyProportionChange change =
                            request.BodyProportionChanges[changeIndex];
                        BodyProportionMorphEntry entry =
                            FindBodyProportionEntryByKey(
                                snapshot.Entries,
                                change.Key);
                        if (entry == null ||
                            !ContainsEligibleBodyProportionMorph(
                                currentEntries,
                                entry.Morph))
                        {
                            throw new Exception(
                                "A body-proportion key is stale or no longer " +
                                "eligible.");
                        }
                        if (change.Value < entry.Minimum ||
                            change.Value > entry.Maximum)
                        {
                            throw new Exception(
                                "A body-proportion value is outside its " +
                                "published safe range.");
                        }
                        float oldValue = entry.Morph.morphValue;
                        if (!IsFinite(oldValue) ||
                            Mathf.Abs(change.Value - oldValue) >
                                MaximumBodyProportionDelta + 0.0001f)
                        {
                            throw new Exception(
                                "A body-proportion change exceeds the " +
                                "maximum 0.25 step.");
                        }
                        if (Mathf.Abs(change.Value - oldValue) <=
                            0.000001f)
                        {
                            continue;
                        }
                        BodyProportionUndoValue old =
                            new BodyProportionUndoValue();
                        old.Morph = entry.Morph;
                        old.Value = oldValue;
                        newUndo.Values.Add(old);
                        BodyProportionUndoValue rollbackValue =
                            new BodyProportionUndoValue();
                        rollbackValue.Morph = entry.Morph;
                        rollbackValue.Value = oldValue;
                        rollback.Add(rollbackValue);
                        SetBodyProportionMorphValue(
                            entry.Morph,
                            change.Value);
                    }
                    if (newUndo.Values.Count == 0)
                    {
                        throw new Exception(
                            "No body-proportion morph values changed; " +
                            "refresh the analysis before applying again.");
                    }
                    List<BodyProportionMorphEntry> appliedEntries =
                        GetBodyProportionMorphEntries(geometry);
                    newUndo.PostApplyMorphStateKey =
                        BuildBodyProportionMorphStateKey(
                            geometry,
                            appliedEntries);
                    _personBodyProportionUndo[
                        request.TargetUid] = newUndo;
                    undoBookkeepingChanged = true;
                }

                SuperController.singleton.ResetSimulation(
                    Sam3dPhysicsResetFrames,
                    undo
                    ? "Restore VAM-PIP body proportions"
                    : "Apply VAM-PIP body proportions",
                    true);
                _personBodyProportionSnapshots.Remove(
                    request.TargetUid);
                CompleteRequest(request.RequestId);
                PublishSceneStatus();
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    "vam",
                    undo
                    ? "Previous body proportions restored."
                    : "Body-proportion morphs applied; exact undo is available.");
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] " +
                    (undo
                    ? "Body proportions restored on "
                    : "Body proportions applied to ") +
                    request.TargetUid +
                    ".");
            }
            catch (Exception exception)
            {
                string rollbackError = "";
                if (rollback.Count != 0)
                {
                    try
                    {
                        RestoreBodyProportionValues(rollback);
                    }
                    catch (Exception rollbackException)
                    {
                        rollbackError =
                            " Rollback also failed: " +
                            DescribeException(rollbackException);
                    }
                }
                if (undoBookkeepingChanged)
                {
                    if (priorUndoPresent && priorUndo != null)
                    {
                        _personBodyProportionUndo[
                            request.TargetUid] = priorUndo;
                    }
                    else
                    {
                        _personBodyProportionUndo.Remove(
                            request.TargetUid);
                    }
                }
                FailRequest(
                    request,
                    startedAt,
                    "Person body-proportion request failed: " +
                    DescribeException(exception) +
                    rollbackError);
            }
        }

        private IEnumerator ExecuteLoadScene(BridgeRequest request)
        {
            string startedAt = UtcNow();
            string prepareError = "";
            bool rescanAttempted = false;

            try
            {
                if (request.RescanRequired)
                {
                    rescanAttempted = true;
                    PublishStatus(
                        StateRescanning,
                        request.RequestId,
                        startedAt,
                        "",
                        "",
                        "Rescanning VaM packages before loading the scene.");
                    SuperController.singleton.RescanPackages();
                }

                if (!FileManagerSecure.FileExists(request.ResourceRef))
                {
                    throw new Exception(
                        "The validated scene does not exist or is not visible to VaM.");
                }
            }
            catch (Exception exception)
            {
                prepareError =
                    "Scene load request failed: " +
                    DescribeException(exception);
            }
            finally
            {
                if (rescanAttempted)
                {
                    _nextAllowedRescanAt =
                        Time.realtimeSinceStartup +
                        MinimumRescanIntervalSeconds;
                }
            }

            if (prepareError.Length != 0)
            {
                FinishSceneLoadError(request, startedAt, prepareError);
                yield break;
            }

            PublishStatus(
                StateLoadingScene,
                request.RequestId,
                startedAt,
                "",
                "vam",
                request.Merge
                ? "Merging scene."
                : "Loading scene.");

            string loadError = "";
            try
            {
                string normalizedPath =
                    FileManagerSecure.NormalizePath(request.ResourceRef);
                if (request.Merge)
                {
                    SuperController.singleton.LoadMerge(normalizedPath);
                }
                else
                {
                    SuperController.singleton.Load(normalizedPath);
                }
            }
            catch (Exception exception)
            {
                loadError =
                    "Could not dispatch scene load: " +
                    DescribeException(exception);
            }
            if (loadError.Length != 0)
            {
                FinishSceneLoadError(request, startedAt, loadError);
                yield break;
            }

            // VaM raises isLoading asynchronously, so always cross a frame
            // boundary before deciding that the operation has completed.
            yield return new WaitForEndOfFrame();

            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (SuperController.singleton != null &&
                   SuperController.singleton.isLoading &&
                   Time.realtimeSinceStartup < deadline)
            {
                yield return null;
            }

            if (SuperController.singleton == null)
            {
                FinishSceneLoadError(
                    request,
                    startedAt,
                    "VaM's scene controller became unavailable while loading.");
                yield break;
            }
            if (SuperController.singleton.isLoading)
            {
                FinishSceneLoadError(
                    request,
                    startedAt,
                    "Scene loading did not finish within 120 seconds.");
                yield break;
            }

            CompleteRequest(request.RequestId);
            _pendingRequest = null;
            _requestInProgress = false;
            PublishSceneStatus();
            PublishStatus(
                StateOk,
                request.RequestId,
                startedAt,
                UtcNow(),
                "vam",
                request.Merge
                ? "Scene merged."
                : "Scene loaded.");
            SuperController.LogMessage(
                "[VAM-PIP Bridge] " +
                (request.Merge ? "Merged " : "Loaded ") +
                request.ResourceRef +
                ".");
        }

        private void FinishSceneLoadError(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            _pendingRequest = null;
            _requestInProgress = false;
            FailRequest(request, startedAt, message);
        }

        private IEnumerator ExecuteAddAtom(
            BridgeRequest request,
            string atomType)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateAdding,
                request.RequestId,
                startedAt,
                "",
                "",
                "Adding " + atomType + " " + request.TargetUid + ".");

            Atom existing = null;
            IEnumerator addRoutine = null;
            string addError = "";
            try
            {
                existing =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (existing == null)
                {
                    addRoutine =
                        SuperController.singleton.AddAtomByType(
                            atomType,
                            request.TargetUid,
                            true);
                    if (addRoutine == null)
                    {
                        throw new Exception(
                            "VaM did not provide an atom creation routine.");
                    }
                }
            }
            catch (Exception exception)
            {
                addError =
                    "Could not add " + atomType + ": " +
                    DescribeException(exception);
            }
            if (addError.Length != 0)
            {
                FinishAtomActionError(
                    request,
                    startedAt,
                    addError);
                yield break;
            }

            if (existing != null)
            {
                if (existing.type != atomType)
                {
                    FinishAtomActionError(
                        request,
                        startedAt,
                        "targetUid is already used by an atom of type " +
                        existing.type +
                        ", not " +
                        atomType +
                        ".");
                    yield break;
                }
                FinishAtomActionOk(
                    request,
                    startedAt,
                    atomType +
                    " already exists; no scene change was needed.");
                yield break;
            }

            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (true)
            {
                bool hasNext = false;
                object current = null;
                string iterationError = "";
                if (Time.realtimeSinceStartup >= deadline)
                {
                    iterationError =
                        atomType + " creation did not finish within 120 seconds.";
                }
                else
                {
                    try
                    {
                        hasNext = addRoutine.MoveNext();
                        if (hasNext)
                        {
                            current = addRoutine.Current;
                        }
                    }
                    catch (Exception exception)
                    {
                        iterationError =
                            atomType + " creation failed: " +
                            DescribeException(exception);
                    }
                }
                if (iterationError.Length != 0)
                {
                    FinishAtomActionError(
                        request,
                        startedAt,
                        iterationError);
                    yield break;
                }
                if (!hasNext)
                {
                    break;
                }
                yield return current;
            }

            yield return new WaitForEndOfFrame();

            try
            {
                Atom created =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (created == null || created.type != atomType)
                {
                    throw new Exception(
                        "VaM completed creation without the requested " +
                        atomType +
                        " atom.");
                }
                FinishAtomActionOk(
                    request,
                    startedAt,
                    atomType + " added.");
            }
            catch (Exception exception)
            {
                FinishAtomActionError(
                    request,
                    startedAt,
                    "Could not verify the added " +
                    atomType +
                    ": " +
                    DescribeException(exception));
            }
        }

        private void FinishAtomActionOk(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            CompleteRequest(request.RequestId);
            _pendingRequest = null;
            _requestInProgress = false;
            PublishSceneStatus();
            PublishStatus(
                StateOk,
                request.RequestId,
                startedAt,
                UtcNow(),
                "vam",
                message);
            SuperController.LogMessage(
                "[VAM-PIP Bridge] " + message);
        }

        private void FinishAtomActionError(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            _pendingRequest = null;
            _requestInProgress = false;
            FailRequest(request, startedAt, message);
        }

        private static bool IsSam3dControllerId(string id)
        {
            const string allowed =
                "|hipControl|lThighControl|rThighControl|" +
                "lKneeControl|rKneeControl|lFootControl|rFootControl|" +
                "abdomen2Control|chestControl|neckControl|headControl|" +
                "lShoulderControl|rShoulderControl|" +
                "lArmControl|rArmControl|lElbowControl|rElbowControl|" +
                "lHandControl|rHandControl|";
            return id != null &&
                id.IndexOf('|') < 0 &&
                allowed.IndexOf(
                    "|" + id + "|",
                    StringComparison.Ordinal) >= 0;
        }

        private static Vector3 ParseSam3dVector(
            JSONNode node,
            string label)
        {
            JSONArray values = node == null ? null : node.AsArray;
            if (values == null || values.Count != 3)
            {
                throw new Exception(label + " must contain three numbers.");
            }
            float x = values[0].AsFloat;
            float y = values[1].AsFloat;
            float z = values[2].AsFloat;
            if (!IsFinite(x) || !IsFinite(y) || !IsFinite(z) ||
                Mathf.Abs(x) > MaximumSam3dCoordinate ||
                Mathf.Abs(y) > MaximumSam3dCoordinate ||
                Mathf.Abs(z) > MaximumSam3dCoordinate)
            {
                throw new Exception(
                    label + " contains a non-finite or out-of-range coordinate.");
            }
            return new Vector3(x, y, z);
        }

        private static Quaternion ParseSam3dQuaternion(
            JSONNode node,
            string label)
        {
            JSONArray values = node == null ? null : node.AsArray;
            if (values == null || values.Count != 4)
            {
                throw new Exception(label + " must contain four numbers.");
            }
            float x = values[0].AsFloat;
            float y = values[1].AsFloat;
            float z = values[2].AsFloat;
            float w = values[3].AsFloat;
            if (!IsFinite(x) || !IsFinite(y) ||
                !IsFinite(z) || !IsFinite(w))
            {
                throw new Exception(label + " contains a non-finite value.");
            }
            float magnitude =
                Mathf.Sqrt(x * x + y * y + z * z + w * w);
            if (!IsFinite(magnitude) ||
                magnitude < 0.5f ||
                magnitude > 1.5f)
            {
                throw new Exception(
                    label + " is not a bounded unit quaternion.");
            }
            return new Quaternion(
                x / magnitude,
                y / magnitude,
                z / magnitude,
                w / magnitude);
        }

        private static string Sam3dText(
            JSONNode node,
            string label,
            int maximumLength)
        {
            string value = ((string)node ?? "").Trim();
            if (value.Length == 0 || value.Length > maximumLength ||
                ContainsControlCharacter(value))
            {
                throw new Exception(
                    label + " must contain 1 to " +
                    maximumLength +
                    " printable characters.");
            }
            return value;
        }

        private static uint Sha256RotateRight(uint value, int count)
        {
            return (value >> count) | (value << (32 - count));
        }

        private static string Sha256Ascii(string value)
        {
            if (value == null)
            {
                throw new Exception("Cannot hash a null SAM3D solution.");
            }
            byte[] input = new byte[value.Length];
            int index;
            for (index = 0; index < value.Length; index++)
            {
                if (value[index] > 127)
                {
                    throw new Exception(
                        "The SAM3D solution must use ASCII JSON encoding.");
                }
                input[index] = (byte)value[index];
            }
            return Sha256Bytes(input);
        }

        private static string Sha256Bytes(byte[] input)
        {
            if (input == null)
            {
                throw new Exception("Cannot hash null SAM3D reference data.");
            }
            int index;
            int paddedLength =
                ((input.Length + 9 + 63) / 64) * 64;
            byte[] message = new byte[paddedLength];
            Array.Copy(input, message, input.Length);
            message[input.Length] = 0x80;
            ulong bitLength = (ulong)input.Length * 8UL;
            for (index = 0; index < 8; index++)
            {
                message[paddedLength - 1 - index] =
                    (byte)(bitLength >> (index * 8));
            }

            uint[] constants = new uint[] {
                0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u,
                0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
                0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
                0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
                0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
                0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
                0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
                0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
                0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
                0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
                0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u,
                0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
                0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u,
                0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
                0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
                0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u
            };
            uint[] hash = new uint[] {
                0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u
            };
            uint[] schedule = new uint[64];
            unchecked
            {
                int offset;
                for (offset = 0; offset < message.Length; offset += 64)
                {
                    for (index = 0; index < 16; index++)
                    {
                        int cursor = offset + index * 4;
                        schedule[index] =
                            ((uint)message[cursor] << 24) |
                            ((uint)message[cursor + 1] << 16) |
                            ((uint)message[cursor + 2] << 8) |
                            message[cursor + 3];
                    }
                    for (index = 16; index < 64; index++)
                    {
                        uint before15 = schedule[index - 15];
                        uint before2 = schedule[index - 2];
                        uint sigma0 =
                            Sha256RotateRight(before15, 7) ^
                            Sha256RotateRight(before15, 18) ^
                            (before15 >> 3);
                        uint sigma1 =
                            Sha256RotateRight(before2, 17) ^
                            Sha256RotateRight(before2, 19) ^
                            (before2 >> 10);
                        schedule[index] =
                            schedule[index - 16] +
                            sigma0 +
                            schedule[index - 7] +
                            sigma1;
                    }

                    uint a = hash[0];
                    uint b = hash[1];
                    uint c = hash[2];
                    uint d = hash[3];
                    uint e = hash[4];
                    uint f = hash[5];
                    uint g = hash[6];
                    uint h = hash[7];
                    for (index = 0; index < 64; index++)
                    {
                        uint sum1 =
                            Sha256RotateRight(e, 6) ^
                            Sha256RotateRight(e, 11) ^
                            Sha256RotateRight(e, 25);
                        uint choose = (e & f) ^ ((~e) & g);
                        uint temporary1 =
                            h +
                            sum1 +
                            choose +
                            constants[index] +
                            schedule[index];
                        uint sum0 =
                            Sha256RotateRight(a, 2) ^
                            Sha256RotateRight(a, 13) ^
                            Sha256RotateRight(a, 22);
                        uint majority =
                            (a & b) ^ (a & c) ^ (b & c);
                        uint temporary2 = sum0 + majority;
                        h = g;
                        g = f;
                        f = e;
                        e = d + temporary1;
                        d = c;
                        c = b;
                        b = a;
                        a = temporary1 + temporary2;
                    }
                    hash[0] += a;
                    hash[1] += b;
                    hash[2] += c;
                    hash[3] += d;
                    hash[4] += e;
                    hash[5] += f;
                    hash[6] += g;
                    hash[7] += h;
                }
            }

            const string hexadecimal = "0123456789abcdef";
            char[] result = new char[64];
            for (index = 0; index < hash.Length; index++)
            {
                int digit;
                for (digit = 0; digit < 8; digit++)
                {
                    int shift = 28 - digit * 4;
                    result[index * 8 + digit] =
                        hexadecimal[
                            (int)((hash[index] >> shift) & 0x0fu)];
                }
            }
            return new string(result);
        }

        private static Sam3dSolution LoadSam3dSolution(
            BridgeRequest request)
        {
            string path =
                Sam3dRoot + "\\" + request.Sam3dJobId + ".json";
            if (!FileManagerSecure.FileExists(path))
            {
                throw new Exception(
                    "The requested SAM3D solution is not available.");
            }
            string payload = FileManagerSecure.ReadAllText(path);
            if (payload == null || payload.Length == 0 ||
                payload.Length > 131072)
            {
                throw new Exception(
                    "The SAM3D solution is empty or exceeds 128 KiB.");
            }
            if (!string.Equals(
                    Sha256Ascii(payload),
                    request.Sam3dSolutionSha256,
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new Exception(
                    "The SAM3D solution file digest no longer matches the request.");
            }
            JSONClass document = JSON.Parse(payload).AsObject;
            if (document == null ||
                document["schema"].AsInt != Sam3dSolutionSchema)
            {
                throw new Exception(
                    "The SAM3D solution schema is unsupported.");
            }

            Sam3dSolution solution = new Sam3dSolution();
            solution.JobId =
                ((string)document["jobId"] ?? "").Trim().ToLowerInvariant();
            solution.Revision =
                ((string)document["revision"] ?? "").Trim().ToLowerInvariant();
            if (!string.Equals(
                    solution.JobId,
                    request.Sam3dJobId,
                    StringComparison.OrdinalIgnoreCase) ||
                !string.Equals(
                    solution.Revision,
                    request.Sam3dRevision,
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new Exception(
                    "The SAM3D solution no longer matches the requested revision.");
            }
            if ((string)document["coordinateSpace"] !=
                Sam3dCoordinateSpace)
            {
                throw new Exception(
                    "The SAM3D solution coordinate space is unsupported.");
            }

            JSONArray controllers = document["controllers"].AsArray;
            if (controllers == null ||
                controllers.Count != Sam3dControllerCount)
            {
                throw new Exception(
                    "The SAM3D solution must contain exactly 19 controllers.");
            }
            solution.Controllers =
                new List<Sam3dControllerSolution>();
            HashSet<string> seen = new HashSet<string>();
            int controllerIndex;
            for (controllerIndex = 0;
                 controllerIndex < controllers.Count;
                 controllerIndex++)
            {
                JSONClass value = controllers[controllerIndex].AsObject;
                string id =
                    value == null
                    ? ""
                    : ((string)value["id"] ?? "").Trim();
                if (!IsSam3dControllerId(id) || seen.Contains(id))
                {
                    throw new Exception(
                        "The SAM3D solution contains an unknown or duplicate controller.");
                }
                seen.Add(id);
                Sam3dControllerSolution controller =
                    new Sam3dControllerSolution();
                controller.Id = id;
                controller.Position =
                    ParseSam3dVector(
                        value["position"],
                        id + " position");
                controller.Rotation =
                    ParseSam3dQuaternion(
                        value["rotation"],
                        id + " rotation");
                solution.Controllers.Add(controller);
            }

            JSONClass camera = document["camera"].AsObject;
            if (camera == null)
            {
                throw new Exception(
                    "The SAM3D solution has no camera.");
            }
            solution.Camera = new Sam3dCameraSolution();
            solution.Camera.Position =
                ParseSam3dVector(camera["position"], "camera position");
            solution.Camera.Rotation =
                ParseSam3dQuaternion(camera["rotation"], "camera rotation");
            solution.Camera.FlatHorizontalFov =
                camera["flatHorizontalFov"].AsFloat;
            if (!IsFinite(solution.Camera.FlatHorizontalFov) ||
                solution.Camera.FlatHorizontalFov < 0.1f ||
                solution.Camera.FlatHorizontalFov > 179.9f)
            {
                throw new Exception(
                    "camera flatHorizontalFov must be between 0.1 and 179.9.");
            }
            solution.Camera.AspectRatio =
                Sam3dText(camera["aspectRatio"], "camera aspectRatio", 16);
            solution.Camera.OutputResolution =
                Sam3dText(
                    camera["outputResolution"],
                    "camera outputResolution",
                    64);
            solution.Camera.ImageFormat =
                Sam3dText(camera["imageFormat"], "camera imageFormat", 128);
            solution.Camera.BaseFilename =
                Sam3dText(camera["basename"], "camera basename", 64);
            if (solution.Camera.BaseFilename != solution.JobId)
            {
                throw new Exception(
                    "camera basename does not match the immutable job ID.");
            }
            return solution;
        }

        private static void ValidateSam3dReferenceFile(
            BridgeRequest request)
        {
            string path =
                request.Sam3dReferenceResourceRef ?? "";
            if (!FileManagerSecure.FileExists(path))
            {
                throw new Exception(
                    "The staged SAM3D reference image is not visible to VaM.");
            }
            byte[] payload = FileManagerSecure.ReadAllBytes(path);
            if (payload == null ||
                payload.Length == 0 ||
                payload.Length > Sam3dReferenceMaximumBytes)
            {
                throw new Exception(
                    "The staged SAM3D reference image is empty or exceeds 32 MiB.");
            }
            if (!string.Equals(
                    Sha256Bytes(payload),
                    request.Sam3dReferenceSha256,
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new Exception(
                    "The staged SAM3D reference image digest no longer matches the request.");
            }
        }

        private static JSONStorableUrl RequireSam3dReferenceUrl(
            Atom atom)
        {
            if (atom == null ||
                atom.type != Sam3dReferenceAtomType ||
                atom.uid != Sam3dReferenceUid)
            {
                throw new Exception(
                    "The fixed SAM3D reference atom identity is invalid.");
            }
            JSONStorable image =
                atom.GetStorableByID("Image");
            JSONStorableUrl url =
                image == null
                ? null
                : image.GetUrlJSONParam("url");
            if (url == null)
            {
                throw new Exception(
                    "The SAM3D reference ImagePanel has no Image/url parameter.");
            }
            return url;
        }

        private static JSONStorableFloat RequireSam3dReferenceScale(
            Atom atom,
            string name)
        {
            JSONStorable scale =
                atom == null
                ? null
                : atom.GetStorableByID("scale");
            JSONStorableFloat value =
                scale == null
                ? null
                : scale.GetFloatJSONParam(name);
            if (value == null)
            {
                throw new Exception(
                    "The SAM3D reference ImagePanel has no scale/" +
                    name +
                    " parameter.");
            }
            return value;
        }

        private static bool IsOwnedSam3dReferencePath(
            string value)
        {
            if (value == null)
            {
                return false;
            }
            string path = value.Trim().Replace('\\', '/');
            if (!path.StartsWith(
                    Sam3dReferencePrefix,
                    StringComparison.Ordinal))
            {
                return false;
            }
            string basename =
                path.Substring(Sam3dReferencePrefix.Length);
            if (basename.Length != 36 &&
                basename.Length != 37)
            {
                return false;
            }
            int extensionOffset = basename.LastIndexOf('.');
            if (extensionOffset != 32 ||
                !IsHexToken(basename.Substring(0, 32)))
            {
                return false;
            }
            string extension =
                basename.Substring(extensionOffset).ToLowerInvariant();
            return extension == ".jpg" ||
                extension == ".jpeg" ||
                extension == ".png";
        }

        private static Sam3dReferenceState CloneSam3dReferenceState(
            Sam3dReferenceState value)
        {
            if (value == null)
            {
                return null;
            }
            Sam3dReferenceState copy =
                new Sam3dReferenceState();
            copy.Atom = value.Atom;
            copy.JobId = value.JobId;
            copy.JobRevision = value.JobRevision;
            copy.SolutionRevision = value.SolutionRevision;
            copy.TargetUid = value.TargetUid;
            copy.ResourceRef = value.ResourceRef;
            copy.ResourceSha256 = value.ResourceSha256;
            copy.SourceWidth = value.SourceWidth;
            copy.SourceHeight = value.SourceHeight;
            copy.AlignedToPose = value.AlignedToPose;
            return copy;
        }

        private Sam3dReferenceState CurrentSam3dReferenceState()
        {
            Sam3dReferenceState state =
                _sam3dReferenceState;
            if (state == null ||
                SuperController.singleton == null)
            {
                return null;
            }
            Atom current =
                SuperController.singleton.GetAtomByUid(
                    Sam3dReferenceUid);
            if (current == null ||
                current.type != Sam3dReferenceAtomType ||
                !object.ReferenceEquals(current, state.Atom))
            {
                _sam3dReferenceState = null;
                return null;
            }
            JSONStorableUrl url = null;
            try
            {
                url = RequireSam3dReferenceUrl(current);
            }
            catch
            {
                _sam3dReferenceState = null;
                return null;
            }
            if (!IsOwnedSam3dReferencePath(url.val) ||
                !string.Equals(
                    (url.val ?? "").Replace('\\', '/'),
                    state.ResourceRef,
                    StringComparison.Ordinal))
            {
                _sam3dReferenceState = null;
                return null;
            }
            return state;
        }

        private static Sam3dReferenceSnapshot SnapshotSam3dReference(
            Atom atom,
            bool created)
        {
            Sam3dReferenceSnapshot snapshot =
                new Sam3dReferenceSnapshot();
            snapshot.Atom = atom;
            snapshot.Created = created;
            if (created)
            {
                return snapshot;
            }
            snapshot.On = atom.on;
            snapshot.CollisionEnabled = atom.collisionEnabled;
            snapshot.Controller = atom.mainController;
            if (snapshot.Controller == null ||
                snapshot.Controller.control == null)
            {
                throw new Exception(
                    "The SAM3D reference ImagePanel has no main controller.");
            }
            snapshot.Position =
                snapshot.Controller.control.position;
            snapshot.Rotation =
                snapshot.Controller.control.rotation;
            snapshot.PositionState =
                snapshot.Controller.currentPositionState;
            snapshot.RotationState =
                snapshot.Controller.currentRotationState;
            snapshot.PhysicsEnabled =
                snapshot.Controller.physicsEnabled;
            snapshot.PhysicalBody =
                snapshot.Controller.followWhenOffRB;
            snapshot.PhysicalBodyWasPresent =
                !object.ReferenceEquals(
                    snapshot.PhysicalBody,
                    null);
            if (snapshot.PhysicalBodyWasPresent)
            {
                if (snapshot.PhysicalBody == null)
                {
                    throw new Exception(
                        "The SAM3D reference physical body was destroyed.");
                }
                snapshot.PhysicalBodyKinematic =
                    snapshot.PhysicalBody.isKinematic;
            }
            snapshot.Url =
                RequireSam3dReferenceUrl(atom);
            snapshot.UrlValue =
                snapshot.Url.val ?? "";
            snapshot.Scale =
                RequireSam3dReferenceScale(atom, "scale");
            snapshot.ScaleValue =
                snapshot.Scale.val;
            snapshot.ScaleX =
                RequireSam3dReferenceScale(atom, "scaleX");
            snapshot.ScaleXValue =
                snapshot.ScaleX.val;
            snapshot.ScaleY =
                RequireSam3dReferenceScale(atom, "scaleY");
            snapshot.ScaleYValue =
                snapshot.ScaleY.val;
            JSONStorable scale =
                atom.GetStorableByID("scale");
            snapshot.ScaleZ =
                scale == null
                ? null
                : scale.GetFloatJSONParam("scaleZ");
            if (snapshot.ScaleZ != null)
            {
                snapshot.ScaleZValue =
                    snapshot.ScaleZ.val;
            }
            return snapshot;
        }

        private static void RestoreSam3dReferenceSnapshot(
            Sam3dReferenceSnapshot snapshot)
        {
            if (snapshot == null)
            {
                return;
            }
            if (SuperController.singleton == null)
            {
                throw new Exception(
                    "VaM's scene controller is unavailable while restoring the reference.");
            }
            Atom current =
                SuperController.singleton.GetAtomByUid(
                    Sam3dReferenceUid);
            if (snapshot.Created)
            {
                if (current == null)
                {
                    return;
                }
                if (current.type != Sam3dReferenceAtomType ||
                    !object.ReferenceEquals(current, snapshot.Atom))
                {
                    throw new Exception(
                        "The generated SAM3D reference identity changed.");
                }
                SuperController.singleton.RemoveAtom(current);
                return;
            }
            if (current == null ||
                !object.ReferenceEquals(current, snapshot.Atom) ||
                snapshot.Controller == null ||
                snapshot.Controller.control == null)
            {
                throw new Exception(
                    "The saved SAM3D reference is no longer available.");
            }
            snapshot.Url.val =
                snapshot.UrlValue;
            snapshot.Scale.val =
                snapshot.ScaleValue;
            snapshot.ScaleX.val =
                snapshot.ScaleXValue;
            snapshot.ScaleY.val =
                snapshot.ScaleYValue;
            if (snapshot.ScaleZ != null)
            {
                snapshot.ScaleZ.val =
                    snapshot.ScaleZValue;
            }
            current.SetOn(snapshot.On);
            current.collisionEnabled =
                snapshot.CollisionEnabled;
            snapshot.Controller.currentPositionState =
                snapshot.PositionState;
            snapshot.Controller.currentRotationState =
                snapshot.RotationState;
            snapshot.Controller.physicsEnabled =
                snapshot.PhysicsEnabled;
            snapshot.Controller.control.position =
                snapshot.Position;
            snapshot.Controller.control.rotation =
                snapshot.Rotation;
            if (snapshot.PhysicalBodyWasPresent)
            {
                if (snapshot.PhysicalBody == null)
                {
                    throw new Exception(
                        "The saved SAM3D reference physical body is unavailable.");
                }
                snapshot.PhysicalBody.isKinematic =
                    snapshot.PhysicalBodyKinematic;
                snapshot.PhysicalBody.position =
                    snapshot.Position;
                snapshot.PhysicalBody.rotation =
                    snapshot.Rotation;
            }
            if (snapshot.Controller.onPositionChangeHandlers != null)
            {
                snapshot.Controller.onPositionChangeHandlers(
                    snapshot.Controller);
            }
        }

        private static void ConfigureSam3dReference(
            BridgeRequest request,
            Sam3dSolution solution,
            Atom person,
            Atom reference,
            bool alignedToPose)
        {
            if (person == null ||
                person.type != "Person")
            {
                throw new Exception(
                    "The SAM3D reference target is not an existing Person.");
            }
            FreeControllerV3 hip =
                person.GetStorableByID("hipControl")
                as FreeControllerV3;
            if (hip == null ||
                hip.control == null)
            {
                throw new Exception(
                    "The SAM3D reference Person has no hipControl.");
            }
            Vector3 anchorPosition =
                hip.control.position;
            Quaternion anchorRotation =
                Sam3dAnchorRotation(person);
            Vector3 cameraPosition =
                anchorPosition +
                anchorRotation *
                    solution.Camera.Position;
            Quaternion cameraRotation =
                anchorRotation *
                    solution.Camera.Rotation;
            Vector3 cameraForward =
                cameraRotation * Vector3.forward;
            float maximumDepth = 0.0f;
            int index;
            for (index = 0;
                 index < solution.Controllers.Count;
                 index++)
            {
                Vector3 world =
                    anchorPosition +
                    anchorRotation *
                        solution.Controllers[index].Position;
                float depth =
                    Vector3.Dot(
                        world - cameraPosition,
                        cameraForward);
                if (depth > maximumDepth)
                {
                    maximumDepth = depth;
                }
            }
            float panelDepth =
                maximumDepth +
                Sam3dReferenceDepthMargin;
            if (!IsFinite(panelDepth) ||
                panelDepth <= 0.05f ||
                panelDepth >
                    Sam3dReferenceMaximumDepth)
            {
                throw new Exception(
                    "The reconstructed reference plane depth is outside safe bounds.");
            }
            float width =
                2.0f *
                panelDepth *
                Mathf.Tan(
                    solution.Camera.FlatHorizontalFov *
                    Mathf.Deg2Rad *
                    0.5f);
            float height =
                width *
                ((float)request.Sam3dReferenceHeight /
                    (float)request.Sam3dReferenceWidth);
            if (!IsFinite(width) ||
                !IsFinite(height) ||
                width <= 0.01f ||
                height <= 0.01f ||
                width > Sam3dReferenceMaximumSize ||
                height > Sam3dReferenceMaximumSize)
            {
                throw new Exception(
                    "The reconstructed reference plane size is outside safe bounds.");
            }

            JSONStorableUrl url =
                RequireSam3dReferenceUrl(reference);
            JSONStorableFloat scale =
                RequireSam3dReferenceScale(reference, "scale");
            JSONStorableFloat scaleX =
                RequireSam3dReferenceScale(reference, "scaleX");
            JSONStorableFloat scaleY =
                RequireSam3dReferenceScale(reference, "scaleY");
            FreeControllerV3 controller =
                reference.mainController;
            if (controller == null ||
                controller.control == null)
            {
                throw new Exception(
                    "The SAM3D reference ImagePanel has no main controller.");
            }
            url.val =
                request.Sam3dReferenceResourceRef;
            scale.val = 1.0f;
            // ImagePanelEmissive already fits the texture's native aspect
            // inside its X/Y scale box. Applying width and height as separate
            // axis scales would apply that ratio a second time (most visibly
            // squeezing portrait references). A square box based on the
            // larger requested dimension lets VaM's native fit reproduce the
            // requested world-space width and height in either orientation.
            float panelExtent = Mathf.Max(width, height);
            scaleX.val = panelExtent;
            scaleY.val = panelExtent;
            reference.SetOn(true);
            reference.collisionEnabled = false;
            controller.physicsEnabled = false;
            if (controller.followWhenOffRB != null)
            {
                controller.followWhenOffRB.isKinematic = true;
            }
            controller.currentPositionState =
                FreeControllerV3.PositionState.On;
            controller.currentRotationState =
                FreeControllerV3.RotationState.On;
            controller.control.position =
                cameraPosition +
                cameraForward *
                    panelDepth;
            controller.control.rotation =
                cameraRotation *
                Quaternion.Euler(0.0f, 180.0f, 0.0f);
            if (controller.onPositionChangeHandlers != null)
            {
                controller.onPositionChangeHandlers(controller);
            }
            SnapSam3dControllerPhysicalPose(controller);
        }

        private IEnumerator EnsureSam3dReference(
            BridgeRequest request,
            Sam3dReferenceResult result)
        {
            result.Atom = null;
            result.Created = false;
            result.Error = "";
            Atom existing = null;
            IEnumerator addRoutine = null;
            try
            {
                existing =
                    SuperController.singleton.GetAtomByUid(
                        Sam3dReferenceUid);
                if (existing != null)
                {
                    if (existing.type != Sam3dReferenceAtomType)
                    {
                        throw new Exception(
                            "The fixed SAM3D reference UID is used by " +
                            existing.type +
                            ".");
                    }
                    string existingUrl =
                        RequireSam3dReferenceUrl(existing).val;
                    if (!IsOwnedSam3dReferencePath(existingUrl))
                    {
                        throw new Exception(
                            "The fixed SAM3D reference UID is not bridge-owned.");
                    }
                    result.Atom = existing;
                    yield break;
                }
                addRoutine =
                    SuperController.singleton.AddAtomByType(
                        Sam3dReferenceAtomType,
                        Sam3dReferenceUid,
                        true);
                if (addRoutine == null)
                {
                    throw new Exception(
                        "VaM did not provide an ImagePanel creation routine.");
                }
                // From this point onward the fixed UID belongs to this
                // transaction, even if VaM fails part-way through creation.
                result.Created = true;
            }
            catch (Exception exception)
            {
                result.Error =
                    "Could not prepare the SAM3D reference: " +
                    DescribeException(exception);
                yield break;
            }

            float deadline =
                Time.realtimeSinceStartup +
                MaximumOperationWaitSeconds;
            while (true)
            {
                bool hasNext = false;
                object current = null;
                try
                {
                    if (Time.realtimeSinceStartup >= deadline)
                    {
                        throw new Exception(
                            "ImagePanel creation did not finish within 120 seconds.");
                    }
                    hasNext = addRoutine.MoveNext();
                    if (hasNext)
                    {
                        current = addRoutine.Current;
                    }
                }
                catch (Exception exception)
                {
                    result.Error =
                        "Could not create the SAM3D reference: " +
                        DescribeException(exception);
                    yield break;
                }
                if (!hasNext)
                {
                    break;
                }
                yield return current;
            }
            yield return new WaitForEndOfFrame();
            try
            {
                Atom created =
                    SuperController.singleton.GetAtomByUid(
                        Sam3dReferenceUid);
                result.Atom = created;
                if (created == null ||
                    created.type != Sam3dReferenceAtomType)
                {
                    throw new Exception(
                        "VaM completed creation without the fixed ImagePanel.");
                }
            }
            catch (Exception exception)
            {
                result.Error =
                    "Could not verify the SAM3D reference: " +
                    DescribeException(exception);
            }
        }

        private string RemoveCreatedSam3dReference(
            Sam3dReferenceResult result)
        {
            if (result == null ||
                !result.Created)
            {
                return "";
            }
            try
            {
                Atom current =
                    SuperController.singleton == null
                    ? null
                    : SuperController.singleton.GetAtomByUid(
                        Sam3dReferenceUid);
                if (current == null)
                {
                    result.Atom = null;
                    result.Created = false;
                    return "";
                }
                if (
                    !object.ReferenceEquals(result.Atom, null) &&
                    !object.ReferenceEquals(
                        current,
                        result.Atom))
                {
                    throw new Exception(
                        "the generated reference identity changed");
                }
                if (current.type != Sam3dReferenceAtomType ||
                    !string.Equals(
                        current.uid,
                        Sam3dReferenceUid,
                        StringComparison.Ordinal))
                {
                    throw new Exception(
                        "the generated reference identity changed");
                }
                SuperController.singleton.RemoveAtom(current);
                if (_sam3dReferenceState != null &&
                    object.ReferenceEquals(
                        _sam3dReferenceState.Atom,
                        current))
                {
                    _sam3dReferenceState = null;
                }
                result.Atom = null;
                result.Created = false;
                return "";
            }
            catch (Exception exception)
            {
                return
                    " Could not remove the generated SAM3D reference: " +
                    DescribeException(exception);
            }
        }

        private static Sam3dReferenceState NewSam3dReferenceState(
            BridgeRequest request,
            Atom atom,
            bool alignedToPose)
        {
            Sam3dReferenceState state =
                new Sam3dReferenceState();
            state.Atom = atom;
            state.JobId =
                (request.Sam3dJobId ?? "").ToLowerInvariant();
            state.JobRevision =
                (request.Sam3dExpectedJobRevision ?? "")
                .ToLowerInvariant();
            state.SolutionRevision =
                (request.Sam3dRevision ?? "").ToLowerInvariant();
            state.TargetUid =
                request.TargetUid ?? "";
            state.ResourceRef =
                request.Sam3dReferenceResourceRef ?? "";
            state.ResourceSha256 =
                (request.Sam3dReferenceSha256 ?? "")
                .ToLowerInvariant();
            state.SourceWidth =
                request.Sam3dReferenceWidth;
            state.SourceHeight =
                request.Sam3dReferenceHeight;
            state.AlignedToPose =
                alignedToPose;
            return state;
        }

        private static MVRScript FindSam3dRenderer(Atom camera)
        {
            if (camera == null || camera.type != "Empty")
            {
                return null;
            }
            List<string> storableIds = camera.GetStorableIDs();
            if (storableIds == null)
            {
                return null;
            }
            int index;
            for (index = 0; index < storableIds.Count; index++)
            {
                string storableId = storableIds[index] ?? "";
                if (!storableId.EndsWith(
                        Sam3dRendererSuffix,
                        StringComparison.Ordinal))
                {
                    continue;
                }
                MVRScript renderer =
                    camera.GetStorableByID(storableId) as MVRScript;
                if (renderer == null ||
                    renderer.GetAction(Sam3dCaptureAction) == null ||
                    renderer.GetStringJSONParam(Sam3dRequestIdParam) == null ||
                    renderer.GetStringJSONParam(Sam3dBaseFilenameParam) == null ||
                    renderer.GetStringJSONParam(Sam3dStatusParam) == null ||
                    renderer.GetStringJSONParam(Sam3dLastOutputParam) == null ||
                    renderer.GetStringJSONParam(Sam3dErrorParam) == null)
                {
                    continue;
                }
                return renderer;
            }
            return null;
        }

        private static JSONStorableStringChooser RequireSam3dChooser(
            MVRScript renderer,
            string name)
        {
            JSONStorableStringChooser chooser =
                renderer.GetStringChooserJSONParam(name);
            if (chooser == null)
            {
                throw new Exception(
                    "The VR-and-Funscript renderer has no " +
                    name +
                    " chooser.");
            }
            return chooser;
        }

        private static void SetSam3dChoice(
            MVRScript renderer,
            string name,
            string value)
        {
            JSONStorableStringChooser chooser =
                RequireSam3dChooser(renderer, name);
            if (chooser.choices == null ||
                !chooser.choices.Contains(value))
            {
                throw new Exception(
                    "The VR-and-Funscript renderer does not support " +
                    name +
                    " value " +
                    value +
                    ".");
            }
            chooser.val = value;
        }

        private static string Sam3dImageFormatLabel(string key)
        {
            if (key == "jpeg")
            {
                return "JPEG (Lossy, Small & Fast)\nNo Transparency";
            }
            if (key == "png")
            {
                return "PNG (Lossless, Big & Slow)\nTransparency Support";
            }
            throw new Exception(
                "camera imageFormat must be either jpeg or png.");
        }

        private static void ConfigureSam3dRenderer(
            MVRScript renderer,
            Sam3dCameraSolution camera)
        {
            JSONStorableFloat fov =
                renderer.GetFloatJSONParam("Flat Horizontal FOV");
            JSONStorableBool funscripts =
                renderer.GetBoolJSONParam("Generate Funscripts");
            if (fov == null || funscripts == null)
            {
                throw new Exception(
                    "The VR-and-Funscript renderer is missing required flat-render controls.");
            }
            SetSam3dChoice(renderer, "Camera Target", "None");
            SetSam3dChoice(renderer, "Render Mode", "Flat");
            SetSam3dChoice(
                renderer,
                "Aspect Ratio",
                camera.AspectRatio);
            SetSam3dChoice(
                renderer,
                "Output Resolution",
                camera.OutputResolution);
            SetSam3dChoice(
                renderer,
                "Image Format",
                Sam3dImageFormatLabel(camera.ImageFormat));
            fov.val = camera.FlatHorizontalFov;
            funscripts.val = false;
        }

        private static Dictionary<string, FreeControllerV3>
            Sam3dPersonControllers(Atom person)
        {
            Dictionary<string, FreeControllerV3> result =
                new Dictionary<string, FreeControllerV3>();
            FreeControllerV3[] controllers =
                person.GetComponentsInChildren<FreeControllerV3>(true);
            int index;
            for (index = 0; index < controllers.Length; index++)
            {
                FreeControllerV3 controller = controllers[index];
                if (controller != null &&
                    IsSam3dControllerId(controller.name) &&
                    !result.ContainsKey(controller.name))
                {
                    result.Add(controller.name, controller);
                }
            }
            return result;
        }

        private static Sam3dUndoSnapshot SnapshotSam3dState(
            BridgeRequest request,
            Sam3dSolution solution,
            Atom person,
            Atom camera,
            MVRScript renderer,
            Dictionary<string, FreeControllerV3> controllers,
            Atom reference,
            bool referenceCreated,
            Sam3dReferenceState previousReferenceState)
        {
            Sam3dUndoSnapshot snapshot = new Sam3dUndoSnapshot();
            snapshot.PersistentHeadLockActive = false;
            snapshot.JobId = solution.JobId;
            snapshot.Revision = solution.Revision;
            snapshot.TargetUid = request.TargetUid;
            snapshot.CameraUid = request.Sam3dCameraUid;
            snapshot.Person = person;
            snapshot.PersonCollisionEnabled = person.collisionEnabled;
            snapshot.Controllers = new List<Sam3dControllerUndo>();
            int index;
            for (index = 0;
                 index < solution.Controllers.Count;
                 index++)
            {
                Sam3dControllerSolution target =
                    solution.Controllers[index];
                FreeControllerV3 controller;
                if (!controllers.TryGetValue(target.Id, out controller) ||
                    controller == null)
                {
                    throw new Exception(
                        "Person is missing required controller " +
                        target.Id +
                        ".");
                }
                Sam3dControllerUndo saved =
                    new Sam3dControllerUndo();
                saved.Controller = controller;
                if (controller.control == null)
                {
                    throw new Exception(
                        "Person controller " +
                        target.Id +
                        " has no authoritative control transform.");
                }
                saved.Position = controller.control.position;
                saved.Rotation = controller.control.rotation;
                saved.PositionState = controller.currentPositionState;
                saved.RotationState = controller.currentRotationState;
                saved.PhysicsEnabled = controller.physicsEnabled;
                saved.PhysicalBody = controller.followWhenOffRB;
                saved.PhysicalBodyWasPresent =
                    !object.ReferenceEquals(
                        saved.PhysicalBody,
                        null);
                if (saved.PhysicalBodyWasPresent)
                {
                    if (saved.PhysicalBody == null)
                    {
                        throw new Exception(
                            "Person controller " +
                            target.Id +
                            " has a destroyed physical body.");
                    }
                    saved.PhysicalBodyKinematic =
                        saved.PhysicalBody.isKinematic;
                }
                snapshot.Controllers.Add(saved);
            }

            snapshot.CameraController = camera.mainController;
            if (snapshot.CameraController == null)
            {
                throw new Exception(
                    "The camera Empty has no main controller.");
            }
            if (snapshot.CameraController.control == null)
            {
                throw new Exception(
                    "The camera Empty has no main control transform.");
            }
            snapshot.CameraPosition =
                snapshot.CameraController.control.position;
            snapshot.CameraRotation =
                snapshot.CameraController.control.rotation;
            snapshot.CameraPositionState =
                snapshot.CameraController.currentPositionState;
            snapshot.CameraRotationState =
                snapshot.CameraController.currentRotationState;
            snapshot.CameraPhysicsEnabled =
                snapshot.CameraController.physicsEnabled;
            snapshot.CameraPhysicalBody =
                snapshot.CameraController.followWhenOffRB;
            snapshot.CameraPhysicalBodyWasPresent =
                !object.ReferenceEquals(
                    snapshot.CameraPhysicalBody,
                    null);
            if (snapshot.CameraPhysicalBodyWasPresent)
            {
                if (snapshot.CameraPhysicalBody == null)
                {
                    throw new Exception(
                        "The camera Empty has a destroyed physical body.");
                }
                snapshot.CameraPhysicalBodyKinematic =
                    snapshot.CameraPhysicalBody.isKinematic;
            }
            snapshot.Renderer = renderer;
            JSONStorableFloat fov =
                renderer.GetFloatJSONParam("Flat Horizontal FOV");
            JSONStorableBool funscripts =
                renderer.GetBoolJSONParam("Generate Funscripts");
            if (fov == null || funscripts == null)
            {
                throw new Exception(
                    "The VR-and-Funscript renderer has incomplete settings.");
            }
            snapshot.FlatHorizontalFov = fov.val;
            snapshot.CameraTarget =
                RequireSam3dChooser(renderer, "Camera Target").val;
            snapshot.AspectRatio =
                RequireSam3dChooser(renderer, "Aspect Ratio").val;
            snapshot.OutputResolution =
                RequireSam3dChooser(renderer, "Output Resolution").val;
            snapshot.RenderMode =
                RequireSam3dChooser(renderer, "Render Mode").val;
            snapshot.ImageFormat =
                RequireSam3dChooser(renderer, "Image Format").val;
            snapshot.GenerateFunscripts = funscripts.val;
            snapshot.PreviousReferenceState =
                CloneSam3dReferenceState(
                    previousReferenceState);
            if (reference != null)
            {
                snapshot.Reference =
                    SnapshotSam3dReference(
                        reference,
                        referenceCreated);
            }
            return snapshot;
        }

        private static void BeginSam3dPoseTransaction(
            Sam3dUndoSnapshot snapshot)
        {
            if (snapshot == null ||
                snapshot.Person == null)
            {
                throw new Exception(
                    "The saved SAM3D Person is no longer available.");
            }
            snapshot.Person.collisionEnabled = false;
            try
            {
                LockSam3dSavedPhysics(snapshot);
            }
            catch
            {
                FinishSam3dPoseTransaction(
                    snapshot,
                    "Cancel VAM-PIP SAM3D pose",
                    false);
                throw;
            }
        }

        private static void LockSam3dSavedPhysics(
            Sam3dUndoSnapshot snapshot)
        {
            ValidateSam3dSavedPhysics(snapshot);
            int index;
            for (index = 0;
                 index < snapshot.Controllers.Count;
                 index++)
            {
                LockSam3dControllerPhysics(
                    snapshot.Controllers[index]);
            }
            LockSam3dCameraPhysics(snapshot);
        }

        private static void ValidateSam3dSavedPhysics(
            Sam3dUndoSnapshot snapshot)
        {
            if (snapshot == null ||
                snapshot.Controllers == null ||
                snapshot.Controllers.Count != Sam3dControllerCount)
            {
                throw new Exception(
                    "The saved SAM3D controller set is incomplete.");
            }
            int index;
            for (index = 0;
                 index < snapshot.Controllers.Count;
                 index++)
            {
                Sam3dControllerUndo saved =
                    snapshot.Controllers[index];
                if (saved == null ||
                    saved.Controller == null ||
                    !IsSam3dSavedPhysicalBodyAvailable(
                        saved.PhysicalBodyWasPresent,
                        saved.PhysicalBody) ||
                    !object.ReferenceEquals(
                        saved.Controller.followWhenOffRB,
                        saved.PhysicalBody))
                {
                    throw new Exception(
                        "A saved Person controller is no longer available.");
                }
            }
            if (snapshot.CameraController == null ||
                !IsSam3dSavedPhysicalBodyAvailable(
                    snapshot.CameraPhysicalBodyWasPresent,
                    snapshot.CameraPhysicalBody) ||
                !object.ReferenceEquals(
                    snapshot.CameraController.followWhenOffRB,
                    snapshot.CameraPhysicalBody))
            {
                throw new Exception(
                    "The saved SAM3D camera is no longer available.");
            }
        }

        private static void LockSam3dControllerPhysics(
            Sam3dControllerUndo saved)
        {
            saved.Controller.physicsEnabled = false;
            if (saved.PhysicalBodyWasPresent)
            {
                saved.PhysicalBody.isKinematic = true;
            }
        }

        private static void RestoreSam3dControllerPhysics(
            Sam3dControllerUndo saved)
        {
            saved.Controller.physicsEnabled =
                saved.PhysicsEnabled;
            if (saved.PhysicalBodyWasPresent)
            {
                saved.PhysicalBody.isKinematic =
                    saved.PhysicalBodyKinematic;
            }
        }

        private static void LockSam3dCameraPhysics(
            Sam3dUndoSnapshot snapshot)
        {
            snapshot.CameraController.physicsEnabled = false;
            if (snapshot.CameraPhysicalBodyWasPresent)
            {
                snapshot.CameraPhysicalBody.isKinematic = true;
            }
        }

        private static bool IsSam3dPersistentHoldController(
            Sam3dControllerUndo saved)
        {
            string id =
                saved == null || saved.Controller == null
                ? ""
                : saved.Controller.name;
            return id == "headControl";
        }

        private static void ReassertSam3dPersistentPoseLock(
            Sam3dUndoSnapshot snapshot)
        {
            ValidateSam3dSavedPhysics(snapshot);
            int index;
            for (index = 0;
                 index < snapshot.Controllers.Count;
                 index++)
            {
                Sam3dControllerUndo saved =
                    snapshot.Controllers[index];
                if (snapshot.PersistentHeadLockActive &&
                    IsSam3dPersistentHoldController(saved))
                {
                    LockSam3dControllerPhysics(saved);
                    SnapSam3dControllerPhysicalPose(
                        saved.Controller);
                }
            }
            LockSam3dCameraPhysics(snapshot);
            SnapSam3dControllerPhysicalPose(
                snapshot.CameraController);
        }

        private static bool IsSam3dSavedPhysicalBodyAvailable(
            bool wasPresent,
            Rigidbody body)
        {
            return wasPresent
                ? body != null
                : object.ReferenceEquals(body, null);
        }

        private static void CommitSam3dPoseLock(
            Sam3dUndoSnapshot snapshot)
        {
            try
            {
                ValidateSam3dSavedPhysics(snapshot);
                int index;
                for (index = 0;
                     index < snapshot.Controllers.Count;
                     index++)
                {
                    Sam3dControllerUndo saved =
                        snapshot.Controllers[index];
                    RestoreSam3dControllerPhysics(saved);
                }
                LockSam3dCameraPhysics(snapshot);
            }
            finally
            {
                try
                {
                    if (snapshot == null ||
                        snapshot.Person == null)
                    {
                        throw new Exception(
                            "The saved SAM3D Person is no longer available.");
                    }
                    snapshot.Person.collisionEnabled =
                        snapshot.PersonCollisionEnabled;
                }
                finally
                {
                    SuperController.singleton.ResetSimulation(
                        Sam3dPhysicsResetFrames,
                        "Lock VAM-PIP SAM3D pose",
                        true);
                }
            }
        }

        private static void RestoreSam3dSavedPhysicsAndCollision(
            Sam3dUndoSnapshot snapshot,
            bool cameraRemovedByUndo)
        {
            if (snapshot == null)
            {
                throw new Exception(
                    "No SAM3D undo snapshot is available.");
            }
            Exception restoreError = null;
            int index;
            if (snapshot.Controllers == null)
            {
                restoreError = new Exception(
                    "The saved SAM3D controller set is unavailable.");
            }
            else
            {
                for (index = 0;
                     index < snapshot.Controllers.Count;
                     index++)
                {
                    Sam3dControllerUndo saved =
                        snapshot.Controllers[index];
                    if (saved == null)
                    {
                        if (restoreError == null)
                        {
                            restoreError = new Exception(
                                "A saved Person controller is no longer available.");
                        }
                        continue;
                    }
                    try
                    {
                        if (saved.Controller == null ||
                            !IsSam3dSavedPhysicalBodyAvailable(
                                saved.PhysicalBodyWasPresent,
                                saved.PhysicalBody) ||
                            !object.ReferenceEquals(
                                saved.Controller.followWhenOffRB,
                                saved.PhysicalBody))
                        {
                            throw new Exception(
                                "A saved Person controller is no longer available.");
                        }
                        saved.Controller.physicsEnabled =
                            saved.PhysicsEnabled;
                    }
                    catch (Exception exception)
                    {
                        if (restoreError == null)
                        {
                            restoreError = exception;
                        }
                    }
                    try
                    {
                        if (!IsSam3dSavedPhysicalBodyAvailable(
                                saved.PhysicalBodyWasPresent,
                                saved.PhysicalBody))
                        {
                            throw new Exception(
                                "A saved Person physical body is no longer available.");
                        }
                        if (saved.PhysicalBodyWasPresent)
                        {
                            saved.PhysicalBody.isKinematic =
                                saved.PhysicalBodyKinematic;
                        }
                    }
                    catch (Exception exception)
                    {
                        if (restoreError == null)
                        {
                            restoreError = exception;
                        }
                    }
                }
            }
            bool cameraControllerAvailable =
                snapshot.CameraController != null;
            bool cameraPhysicalBodyAvailable =
                IsSam3dSavedPhysicalBodyAvailable(
                    snapshot.CameraPhysicalBodyWasPresent,
                    snapshot.CameraPhysicalBody);
            if (cameraControllerAvailable &&
                cameraPhysicalBodyAvailable &&
                object.ReferenceEquals(
                    snapshot.CameraController.followWhenOffRB,
                    snapshot.CameraPhysicalBody))
            {
                try
                {
                    snapshot.CameraController.physicsEnabled =
                        snapshot.CameraPhysicsEnabled;
                }
                catch (Exception exception)
                {
                    if (restoreError == null)
                    {
                        restoreError = exception;
                    }
                }
            }
            else if (!cameraRemovedByUndo &&
                     restoreError == null)
            {
                restoreError = new Exception(
                    "The saved SAM3D camera is no longer available.");
            }
            try
            {
                if (!cameraPhysicalBodyAvailable)
                {
                    if (!cameraRemovedByUndo)
                    {
                        throw new Exception(
                            "The saved SAM3D camera physical body is no longer available.");
                    }
                }
                else if (snapshot.CameraPhysicalBodyWasPresent)
                {
                    snapshot.CameraPhysicalBody.isKinematic =
                        snapshot.CameraPhysicalBodyKinematic;
                }
            }
            catch (Exception exception)
            {
                if (restoreError == null)
                {
                    restoreError = exception;
                }
            }
            try
            {
                if (snapshot.Person == null)
                {
                    throw new Exception(
                        "The saved SAM3D Person is no longer available.");
                }
                snapshot.Person.collisionEnabled =
                    snapshot.PersonCollisionEnabled;
            }
            catch (Exception exception)
            {
                if (restoreError == null)
                {
                    restoreError = exception;
                }
            }
            if (restoreError != null)
            {
                throw restoreError;
            }
        }

        private static void FinishSam3dPoseTransaction(
            Sam3dUndoSnapshot snapshot,
            string reason,
            bool cameraRemovedByUndo)
        {
            try
            {
                RestoreSam3dSavedPhysicsAndCollision(
                    snapshot,
                    cameraRemovedByUndo);
            }
            finally
            {
                SuperController.singleton.ResetSimulation(
                    Sam3dPhysicsResetFrames,
                    reason,
                    true);
            }
        }

        private void RestoreSam3dSnapshot(
            Sam3dUndoSnapshot snapshot)
        {
            if (snapshot == null)
            {
                throw new Exception("No SAM3D undo snapshot is available.");
            }
            bool cameraRemovedByUndo = false;
            BeginSam3dPoseTransaction(snapshot);
            try
            {
                cameraRemovedByUndo =
                    RestoreSam3dSnapshotContents(snapshot);
                if (snapshot.Reference != null)
                {
                    _sam3dReferenceState =
                        CloneSam3dReferenceState(
                            snapshot.PreviousReferenceState);
                }
            }
            finally
            {
                FinishSam3dPoseTransaction(
                    snapshot,
                    "Restore VAM-PIP SAM3D pose",
                    cameraRemovedByUndo);
            }
        }

        private static bool RestoreSam3dSnapshotContents(
            Sam3dUndoSnapshot snapshot)
        {
            int index;
            for (index = 0;
                 index < snapshot.Controllers.Count;
                 index++)
            {
                Sam3dControllerUndo saved =
                    snapshot.Controllers[index];
                if (saved.Controller == null ||
                    saved.Controller.control == null)
                {
                    throw new Exception(
                        "A saved Person controller is no longer available.");
                }
                saved.Controller.currentPositionState =
                    saved.PositionState;
                saved.Controller.currentRotationState =
                    saved.RotationState;
                saved.Controller.control.position = saved.Position;
                saved.Controller.control.rotation = saved.Rotation;
                if (saved.Controller.onPositionChangeHandlers != null)
                {
                    saved.Controller.onPositionChangeHandlers(
                        saved.Controller);
                }
                if (saved.PositionState ==
                        FreeControllerV3.PositionState.Comply ||
                    saved.RotationState ==
                        FreeControllerV3.RotationState.Comply)
                {
                    saved.Controller.PauseComply();
                }
            }
            for (index = 0;
                 index < snapshot.Controllers.Count;
                 index++)
            {
                SnapSam3dControllerPhysicalPose(
                    snapshot.Controllers[index].Controller);
            }
            if (snapshot.Reference != null)
            {
                RestoreSam3dReferenceSnapshot(
                    snapshot.Reference);
            }
            if (snapshot.CameraCreated)
            {
                Atom createdCamera =
                    SuperController.singleton.GetAtomByUid(
                        snapshot.CameraUid);
                if (createdCamera == null ||
                    createdCamera.type != "Empty" ||
                    !object.ReferenceEquals(
                        createdCamera.mainController,
                        snapshot.CameraController) ||
                    !object.ReferenceEquals(
                        FindSam3dRenderer(createdCamera),
                        snapshot.Renderer))
                {
                    throw new Exception(
                        "The generated SAM3D camera is no longer available.");
                }
                SuperController.singleton.RemoveAtom(createdCamera);
                return true;
            }
            if (snapshot.CameraController == null ||
                snapshot.CameraController.control == null ||
                snapshot.Renderer == null)
            {
                throw new Exception(
                    "The saved SAM3D camera is no longer available.");
            }
            snapshot.CameraController.currentPositionState =
                snapshot.CameraPositionState;
            snapshot.CameraController.currentRotationState =
                snapshot.CameraRotationState;
            snapshot.CameraController.control.position =
                snapshot.CameraPosition;
            snapshot.CameraController.control.rotation =
                snapshot.CameraRotation;
            if (snapshot.CameraController.onPositionChangeHandlers != null)
            {
                snapshot.CameraController.onPositionChangeHandlers(
                    snapshot.CameraController);
            }
            if (snapshot.CameraController.followWhenOff != null)
            {
                snapshot.CameraController.followWhenOff.position =
                    snapshot.CameraPosition;
                snapshot.CameraController.followWhenOff.rotation =
                    snapshot.CameraRotation;
            }
            if (snapshot.CameraPositionState ==
                    FreeControllerV3.PositionState.Comply ||
                snapshot.CameraRotationState ==
                    FreeControllerV3.RotationState.Comply)
            {
                snapshot.CameraController.PauseComply();
            }
            snapshot.Renderer.GetFloatJSONParam(
                "Flat Horizontal FOV").val =
                snapshot.FlatHorizontalFov;
            RequireSam3dChooser(
                snapshot.Renderer,
                "Camera Target").val =
                snapshot.CameraTarget;
            RequireSam3dChooser(
                snapshot.Renderer,
                "Aspect Ratio").val =
                snapshot.AspectRatio;
            RequireSam3dChooser(
                snapshot.Renderer,
                "Output Resolution").val =
                snapshot.OutputResolution;
            RequireSam3dChooser(
                snapshot.Renderer,
                "Render Mode").val =
                snapshot.RenderMode;
            RequireSam3dChooser(
                snapshot.Renderer,
                "Image Format").val =
                snapshot.ImageFormat;
            snapshot.Renderer.GetBoolJSONParam(
                "Generate Funscripts").val =
                snapshot.GenerateFunscripts;
            return false;
        }

        private static void SnapSam3dControllerPhysicalPose(
            FreeControllerV3 controller)
        {
            if (controller == null ||
                controller.control == null)
            {
                throw new Exception(
                    "A SAM3D controller has no target transform.");
            }
            Rigidbody physicalBody =
                controller.followWhenOffRB;
            if (physicalBody != null)
            {
                physicalBody.position =
                    controller.control.position;
                physicalBody.rotation =
                    controller.control.rotation;
                physicalBody.velocity = Vector3.zero;
                physicalBody.angularVelocity = Vector3.zero;
                return;
            }
            Transform physicalTransform =
                controller.followWhenOff;
            if (physicalTransform == null)
            {
                throw new Exception(
                    "Person controller " +
                    controller.name +
                    " has no physical transform.");
            }
            physicalTransform.position =
                controller.control.position;
            physicalTransform.rotation =
                controller.control.rotation;
        }

        private Sam3dUndoSnapshot CurrentSam3dSnapshot()
        {
            Sam3dUndoSnapshot snapshot = _sam3dUndoSnapshot;
            if (snapshot == null)
            {
                return null;
            }
            if (SuperController.singleton == null)
            {
                ReleaseSam3dPoseLockWithoutRestoringPose(
                    snapshot,
                    "controller shutdown");
                return null;
            }
            Atom person =
                SuperController.singleton.GetAtomByUid(
                    snapshot.TargetUid);
            Atom camera =
                SuperController.singleton.GetAtomByUid(
                    snapshot.CameraUid);
            if (person == null ||
                person.type != "Person" ||
                !object.ReferenceEquals(
                    person,
                    snapshot.Person) ||
                camera == null ||
                camera.type != "Empty" ||
                snapshot.CameraController == null ||
                !object.ReferenceEquals(
                    camera.mainController,
                    snapshot.CameraController) ||
                !object.ReferenceEquals(
                    FindSam3dRenderer(camera),
                    snapshot.Renderer))
            {
                ReleaseSam3dPoseLockWithoutRestoringPose(
                    snapshot,
                    "invalid applied snapshot");
                return null;
            }
            Dictionary<string, FreeControllerV3> controllers =
                Sam3dPersonControllers(person);
            int index;
            for (index = 0;
                 index < snapshot.Controllers.Count;
                 index++)
            {
                FreeControllerV3 current;
                Sam3dControllerUndo saved =
                    snapshot.Controllers[index];
                if (saved.Controller == null ||
                    !IsSam3dSavedPhysicalBodyAvailable(
                        saved.PhysicalBodyWasPresent,
                        saved.PhysicalBody) ||
                    !controllers.TryGetValue(
                        saved.Controller.name,
                        out current) ||
                    !object.ReferenceEquals(
                        current,
                        saved.Controller) ||
                    !object.ReferenceEquals(
                        saved.Controller.followWhenOffRB,
                        saved.PhysicalBody))
                {
                    ReleaseSam3dPoseLockWithoutRestoringPose(
                        snapshot,
                        "changed Person controller");
                    return null;
                }
            }
            if (snapshot.CameraController == null ||
                !IsSam3dSavedPhysicalBodyAvailable(
                    snapshot.CameraPhysicalBodyWasPresent,
                    snapshot.CameraPhysicalBody) ||
                !object.ReferenceEquals(
                    snapshot.CameraController.followWhenOffRB,
                    snapshot.CameraPhysicalBody))
            {
                ReleaseSam3dPoseLockWithoutRestoringPose(
                    snapshot,
                    "changed camera controller");
                return null;
            }
            if (snapshot.Reference != null)
            {
                Atom reference =
                    SuperController.singleton.GetAtomByUid(
                        Sam3dReferenceUid);
                bool validReference =
                    reference != null &&
                    reference.type == Sam3dReferenceAtomType &&
                    object.ReferenceEquals(
                        reference,
                        snapshot.Reference.Atom);
                if (validReference)
                {
                    try
                    {
                        validReference =
                            IsOwnedSam3dReferencePath(
                                RequireSam3dReferenceUrl(
                                    reference).val);
                    }
                    catch
                    {
                        validReference = false;
                    }
                }
                if (!validReference)
                {
                    ReleaseSam3dPoseLockWithoutRestoringPose(
                        snapshot,
                        "changed reference ImagePanel");
                    return null;
                }
            }
            try
            {
                ReassertSam3dPersistentPoseLock(snapshot);
            }
            catch (Exception exception)
            {
                ReleaseSam3dPoseLockWithoutRestoringPose(
                    snapshot,
                    "pose lock failure: " +
                    DescribeException(exception));
                return null;
            }
            return snapshot;
        }

        private void ReleaseSam3dPoseLockWithoutRestoringPose(
            Sam3dUndoSnapshot snapshot,
            string reason)
        {
            if (snapshot == null)
            {
                return;
            }
            if (object.ReferenceEquals(
                    _sam3dUndoSnapshot,
                    snapshot))
            {
                _sam3dUndoSnapshot = null;
            }
            try
            {
                RestoreSam3dSavedPhysicsAndCollision(
                    snapshot,
                    false);
            }
            catch (Exception exception)
            {
                try
                {
                    SuperController.LogError(
                        "[VAM-PIP Bridge] Could not release the SAM3D " +
                        "physics lock during " +
                        reason +
                        ": " +
                        DescribeException(exception));
                }
                catch
                {
                }
            }
        }

        private static Quaternion Sam3dAnchorRotation(Atom person)
        {
            Transform anchor =
                person.mainController == null
                ? null
                : person.mainController.control;
            if (anchor == null)
            {
                throw new Exception(
                    "The target Person has no main controller.");
            }
            Vector3 forward = anchor.forward;
            forward.y = 0f;
            if (forward.sqrMagnitude < 0.0001f)
            {
                forward = Vector3.forward;
            }
            return Quaternion.LookRotation(
                forward.normalized,
                Vector3.up);
        }

        private static Sam3dApplyDiagnostics NewSam3dApplyDiagnostics(
            BridgeRequest request)
        {
            Sam3dApplyDiagnostics diagnostics =
                new Sam3dApplyDiagnostics();
            diagnostics.RequestId = request.RequestId ?? "";
            diagnostics.CapturedAtUtc = "";
            diagnostics.Error = "";
            diagnostics.Controllers =
                new List<Sam3dControllerDiagnostic>();
            Sam3dControllerDiagnostic head =
                new Sam3dControllerDiagnostic();
            head.Id = "headControl";
            diagnostics.Controllers.Add(head);
            Sam3dControllerDiagnostic neck =
                new Sam3dControllerDiagnostic();
            neck.Id = "neckControl";
            diagnostics.Controllers.Add(neck);
            return diagnostics;
        }

        private static void RecordSam3dRequestedTransform(
            Sam3dApplyDiagnostics diagnostics,
            string id,
            Vector3 position,
            Quaternion rotation)
        {
            if (diagnostics == null ||
                diagnostics.Controllers == null)
            {
                return;
            }
            int index;
            for (index = 0;
                 index < diagnostics.Controllers.Count &&
                 index < Sam3dDiagnosticControllerCount;
                 index++)
            {
                Sam3dControllerDiagnostic item =
                    diagnostics.Controllers[index];
                if (item != null && item.Id == id)
                {
                    item.RequestedPosition = position;
                    item.RequestedRotation = rotation;
                    item.RequestedCaptured = true;
                    return;
                }
            }
        }

        private static void CaptureSam3dSettledDiagnostics(
            Sam3dApplyDiagnostics diagnostics,
            Dictionary<string, FreeControllerV3> controllers)
        {
            if (diagnostics == null ||
                diagnostics.Controllers == null ||
                diagnostics.Controllers.Count !=
                    Sam3dDiagnosticControllerCount)
            {
                throw new Exception(
                    "The fixed SAM3D controller diagnostic set is incomplete.");
            }
            int index;
            for (index = 0;
                 index < Sam3dDiagnosticControllerCount;
                 index++)
            {
                Sam3dControllerDiagnostic item =
                    diagnostics.Controllers[index];
                FreeControllerV3 controller;
                if (item == null ||
                    !item.RequestedCaptured ||
                    controllers == null ||
                    !controllers.TryGetValue(item.Id, out controller) ||
                    controller == null ||
                    controller.control == null)
                {
                    throw new Exception(
                        "Could not inspect settled " +
                        (item == null ? "SAM3D controller" : item.Id) +
                        ".");
                }
                Rigidbody physicalBody =
                    controller.followWhenOffRB;
                Transform physicalTransform =
                    controller.followWhenOff;
                if (physicalBody != null)
                {
                    item.ActualPosition =
                        physicalBody.position;
                    item.ActualRotation =
                        physicalBody.rotation;
                }
                else if (physicalTransform != null)
                {
                    item.ActualPosition =
                        physicalTransform.position;
                    item.ActualRotation =
                        physicalTransform.rotation;
                }
                else
                {
                    throw new Exception(
                        "Could not inspect the physical pose of " +
                        item.Id +
                        ".");
                }
                item.PositionState = controller.currentPositionState;
                item.RotationState = controller.currentRotationState;
                item.PhysicsEnabled = controller.physicsEnabled;
                item.Possessed = controller.possessed;
                item.StartedPossess = controller.startedPossess;
                item.IsGrabbing = controller.isGrabbing;
                item.ActualCaptured = true;
            }
            diagnostics.CapturedAtUtc = UtcNow();
        }

        private static void CaptureSam3dRequestedHeadRotation(
            Sam3dUndoSnapshot snapshot,
            Dictionary<string, FreeControllerV3> controllers)
        {
            FreeControllerV3 head;
            if (snapshot == null ||
                controllers == null ||
                !controllers.TryGetValue(
                    "headControl",
                    out head) ||
                head == null ||
                head.control == null)
            {
                throw new Exception(
                    "The target Person has no usable headControl.");
            }
            snapshot.HeadRequestedRotation =
                head.control.rotation;
            snapshot.HeadRequestedRotationCaptured = true;
        }

        private static void FinalizeSam3dPersistentHeadLock(
            Sam3dUndoSnapshot snapshot)
        {
            ValidateSam3dSavedPhysics(snapshot);
            Sam3dControllerUndo head = null;
            int index;
            for (index = 0;
                 index < snapshot.Controllers.Count;
                 index++)
            {
                Sam3dControllerUndo saved =
                    snapshot.Controllers[index];
                if (IsSam3dPersistentHoldController(saved))
                {
                    head = saved;
                    break;
                }
            }
            if (head == null ||
                head.Controller.control == null ||
                !head.PhysicalBodyWasPresent ||
                !snapshot.HeadRequestedRotationCaptured)
            {
                throw new Exception(
                    "The saved SAM3D head hold is incomplete.");
            }

            Vector3 settledPosition =
                head.PhysicalBody.position;
            LockSam3dControllerPhysics(head);
            head.Controller.control.position =
                settledPosition;
            head.Controller.control.rotation =
                snapshot.HeadRequestedRotation;
            RecordSam3dRequestedTransform(
                snapshot.Diagnostics,
                "headControl",
                settledPosition,
                snapshot.HeadRequestedRotation);
            if (head.Controller.onPositionChangeHandlers != null)
            {
                head.Controller.onPositionChangeHandlers(
                    head.Controller);
            }
            SnapSam3dControllerPhysicalPose(
                head.Controller);
            LockSam3dCameraPhysics(snapshot);
            snapshot.PersistentHeadLockActive = true;
            SuperController.singleton.ResetSimulation(
                Sam3dPhysicsResetFrames,
                "Lock settled VAM-PIP SAM3D head rotation",
                true);
        }

        private static void ApplySam3dTransforms(
            BridgeRequest request,
            Sam3dSolution solution,
            Atom person,
            Atom camera,
            MVRScript renderer,
            Dictionary<string, FreeControllerV3> controllers,
            Atom reference,
            Sam3dUndoSnapshot snapshot,
            Sam3dApplyDiagnostics diagnostics)
        {
            BeginSam3dPoseTransaction(snapshot);
            bool applied = false;
            try
            {
                ApplySam3dTransformContents(
                    request,
                    solution,
                    person,
                    camera,
                    renderer,
                    controllers,
                    reference,
                    diagnostics);
                CaptureSam3dRequestedHeadRotation(
                    snapshot,
                    controllers);
                applied = true;
            }
            finally
            {
                if (applied)
                {
                    CommitSam3dPoseLock(snapshot);
                }
                else
                {
                    FinishSam3dPoseTransaction(
                        snapshot,
                        "Cancel VAM-PIP SAM3D pose",
                        false);
                }
            }
        }

        private static void ApplySam3dTransformContents(
            BridgeRequest request,
            Sam3dSolution solution,
            Atom person,
            Atom camera,
            MVRScript renderer,
            Dictionary<string, FreeControllerV3> controllers,
            Atom reference,
            Sam3dApplyDiagnostics diagnostics)
        {
            FreeControllerV3 hip;
            if (!controllers.TryGetValue("hipControl", out hip) ||
                hip == null)
            {
                throw new Exception(
                    "The target Person has no hipControl.");
            }
            if (hip.control == null)
            {
                throw new Exception(
                    "The target Person hipControl has no authoritative control transform.");
            }
            Vector3 anchorPosition = hip.control.position;
            Quaternion anchorRotation = Sam3dAnchorRotation(person);
            int index;
            for (index = 0;
                 index < solution.Controllers.Count;
                 index++)
            {
                Sam3dControllerSolution target =
                    solution.Controllers[index];
                FreeControllerV3 controller =
                    controllers[target.Id];
                if (controller.control == null)
                {
                    throw new Exception(
                        "Person controller " +
                        target.Id +
                        " has no authoritative control transform.");
                }
                if (controller.currentPositionState ==
                        FreeControllerV3.PositionState.Comply ||
                    controller.currentRotationState ==
                        FreeControllerV3.RotationState.Comply)
                {
                    controller.PauseComply();
                }
                controller.currentPositionState =
                    FreeControllerV3.PositionState.On;
                controller.currentRotationState =
                    FreeControllerV3.RotationState.On;
                Vector3 requestedPosition =
                    anchorPosition +
                    anchorRotation * target.Position;
                Quaternion requestedRotation =
                    anchorRotation * target.Rotation;
                RecordSam3dRequestedTransform(
                    diagnostics,
                    target.Id,
                    requestedPosition,
                    requestedRotation);
                controller.control.position = requestedPosition;
                controller.control.rotation = requestedRotation;
                if (controller.onPositionChangeHandlers != null)
                {
                    controller.onPositionChangeHandlers(controller);
                }
            }
            for (index = 0;
                 index < solution.Controllers.Count;
                 index++)
            {
                Sam3dControllerSolution target =
                    solution.Controllers[index];
                FreeControllerV3 controller =
                    controllers[target.Id];
                SnapSam3dControllerPhysicalPose(controller);
            }

            FreeControllerV3 cameraController = camera.mainController;
            if (cameraController == null ||
                cameraController.control == null)
            {
                throw new Exception(
                    "The camera Empty has no main control transform.");
            }
            cameraController.currentPositionState =
                FreeControllerV3.PositionState.On;
            cameraController.currentRotationState =
                FreeControllerV3.RotationState.On;
            cameraController.control.position =
                anchorPosition +
                anchorRotation * solution.Camera.Position;
            cameraController.control.rotation =
                anchorRotation * solution.Camera.Rotation;
            if (cameraController.onPositionChangeHandlers != null)
            {
                cameraController.onPositionChangeHandlers(
                    cameraController);
            }
            SnapSam3dControllerPhysicalPose(cameraController);
            ConfigureSam3dRenderer(renderer, solution.Camera);
            if (reference != null)
            {
                ConfigureSam3dReference(
                    request,
                    solution,
                    person,
                    reference,
                    true);
            }
        }

        private void FinishSam3dActionOk(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            RecordSam3dAction(request, StateOk, message);
            CompleteRequest(request.RequestId);
            _pendingRequest = null;
            _requestInProgress = false;
            PublishSceneStatus();
            PublishStatus(
                StateOk,
                request.RequestId,
                startedAt,
                UtcNow(),
                "vam-sam3d",
                message);
            SuperController.LogMessage(
                "[VAM-PIP Bridge] " + message);
        }

        private void FinishSam3dActionError(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            RecordSam3dAction(request, StateError, message);
            _pendingRequest = null;
            _requestInProgress = false;
            FailRequest(request, startedAt, message);
        }

        private static IEnumerator WaitForSam3dPhysicsSettlement()
        {
            int frame;
            for (frame = 0;
                 frame < Sam3dPhysicsResetFrames;
                 frame++)
            {
                yield return new WaitForFixedUpdate();
            }
            yield return new WaitForEndOfFrame();
        }

        private static JSONClass Sam3dDiagnosticVector(Vector3 value)
        {
            JSONClass result = new JSONClass();
            result["x"].AsFloat = value.x;
            result["y"].AsFloat = value.y;
            result["z"].AsFloat = value.z;
            return result;
        }

        private static JSONClass Sam3dDiagnosticQuaternion(
            Quaternion value)
        {
            JSONClass result = new JSONClass();
            result["x"].AsFloat = value.x;
            result["y"].AsFloat = value.y;
            result["z"].AsFloat = value.z;
            result["w"].AsFloat = value.w;
            return result;
        }

        private static JSONClass BuildSam3dSettlementStatus(
            Sam3dApplyDiagnostics diagnostics)
        {
            if (diagnostics == null ||
                diagnostics.Controllers == null)
            {
                return null;
            }
            JSONClass result = new JSONClass();
            result["schema"].AsInt = Sam3dDiagnosticSchema;
            result["requestId"] = diagnostics.RequestId ?? "";
            result["capturedAtUtc"] =
                diagnostics.CapturedAtUtc ?? "";
            result["settleFrames"].AsInt =
                Sam3dPhysicsResetFrames;
            result["controllerLimit"].AsInt =
                Sam3dDiagnosticControllerCount;
            result["error"] = diagnostics.Error ?? "";
            bool available =
                (diagnostics.Error ?? "").Length == 0 &&
                diagnostics.Controllers.Count ==
                    Sam3dDiagnosticControllerCount;
            JSONArray controllerResults = new JSONArray();
            int index;
            for (index = 0;
                 index < diagnostics.Controllers.Count &&
                 index < Sam3dDiagnosticControllerCount;
                 index++)
            {
                Sam3dControllerDiagnostic item =
                    diagnostics.Controllers[index];
                if (item == null)
                {
                    available = false;
                    continue;
                }
                JSONClass controller = new JSONClass();
                controller["id"] = item.Id ?? "";
                if (item.RequestedCaptured)
                {
                    JSONClass requested = new JSONClass();
                    requested["position"] =
                        Sam3dDiagnosticVector(
                            item.RequestedPosition);
                    requested["rotation"] =
                        Sam3dDiagnosticQuaternion(
                            item.RequestedRotation);
                    controller["requested"] = requested;
                }
                if (item.ActualCaptured)
                {
                    JSONClass actual = new JSONClass();
                    actual["position"] =
                        Sam3dDiagnosticVector(
                            item.ActualPosition);
                    actual["rotation"] =
                        Sam3dDiagnosticQuaternion(
                            item.ActualRotation);
                    controller["actual"] = actual;
                    controller["positionErrorMeters"].AsFloat =
                        Vector3.Distance(
                            item.RequestedPosition,
                            item.ActualPosition);
                    controller["rotationErrorDegrees"].AsFloat =
                        Quaternion.Angle(
                            item.RequestedRotation,
                            item.ActualRotation);
                    JSONClass state = new JSONClass();
                    state["position"] =
                        item.PositionState.ToString();
                    state["rotation"] =
                        item.RotationState.ToString();
                    state["physicsEnabled"].AsBool =
                        item.PhysicsEnabled;
                    state["possessed"].AsBool =
                        item.Possessed;
                    state["startedPossess"].AsBool =
                        item.StartedPossess;
                    state["isGrabbing"].AsBool =
                        item.IsGrabbing;
                    controller["state"] = state;
                }
                else
                {
                    available = false;
                }
                controllerResults.Add(controller);
            }
            result["available"].AsBool = available;
            result["controllers"] = controllerResults;
            return result;
        }

        private static string RemoveCreatedSam3dCamera(
            BridgeRequest request,
            Sam3dCameraResult result)
        {
            if (result == null || !result.Created)
            {
                return "";
            }
            try
            {
                Atom camera =
                    SuperController.singleton == null
                    ? null
                    : SuperController.singleton.GetAtomByUid(
                        request.Sam3dCameraUid);
                if (camera == null)
                {
                    result.Atom = null;
                    result.Created = false;
                    return "";
                }
                if (
                    !object.ReferenceEquals(result.Atom, null) &&
                    !object.ReferenceEquals(camera, result.Atom))
                {
                    throw new Exception(
                        "the generated camera identity changed");
                }
                if (camera.type != "Empty" ||
                    !string.Equals(
                        camera.uid,
                        request.Sam3dCameraUid,
                        StringComparison.Ordinal))
                {
                    throw new Exception(
                        "the generated camera identity changed");
                }
                SuperController.singleton.RemoveAtom(camera);
                result.Atom = null;
                result.Created = false;
                return "";
            }
            catch (Exception exception)
            {
                return
                    " Could not remove the generated SAM3D camera: " +
                    DescribeException(exception);
            }
        }

        private void RecordSam3dAction(
            BridgeRequest request,
            string state,
            string message)
        {
            if (request == null)
            {
                return;
            }
            _lastSam3dRequestId = request.RequestId ?? "";
            _lastSam3dCommand = request.Command ?? "";
            _lastSam3dJobId = request.Sam3dJobId ?? "";
            _lastSam3dRevision = request.Sam3dRevision ?? "";
            _lastSam3dCameraUid = request.Sam3dCameraUid ?? "";
            _lastSam3dState = state ?? "";
            _lastSam3dMessage = message ?? "";
            if (_lastSam3dMessage.Length > 1000)
            {
                _lastSam3dMessage =
                    _lastSam3dMessage.Substring(0, 1000);
            }
        }

        private IEnumerator EnsureSam3dCamera(
            BridgeRequest request,
            Sam3dCameraResult result)
        {
            result.Atom = null;
            result.Created = false;
            result.Error = "";
            Atom camera =
                SuperController.singleton.GetAtomByUid(
                    request.Sam3dCameraUid);
            if (camera != null)
            {
                if (camera.type != "Empty")
                {
                    result.Error =
                        "cameraUid is already used by an atom of type " +
                        camera.type +
                        ", not Empty.";
                    yield break;
                }
                if (FindSam3dRenderer(camera) == null)
                {
                    result.Error =
                        "The selected Empty does not contain the VAM-PIP-enabled " +
                        "VR Video and Funscript Exporter.";
                    yield break;
                }
                result.Atom = camera;
                yield break;
            }
            if (!request.Sam3dCreateCamera)
            {
                result.Error =
                    "cameraUid does not identify an existing compatible Empty.";
                yield break;
            }
            if (!FileManagerSecure.FileExists(Sam3dCameraPreset))
            {
                result.Error =
                    "The fixed VAM-PIP SAM3D camera preset is not installed.";
                yield break;
            }

            IEnumerator addRoutine = null;
            try
            {
                PublishStatus(
                    StateAdding,
                    request.RequestId,
                    "",
                    "",
                    "vam",
                    "Adding SAM3D VR-and-Funscript camera " +
                    request.Sam3dCameraUid +
                    ".");
                addRoutine =
                    SuperController.singleton.AddAtomByType(
                        "Empty",
                        request.Sam3dCameraUid,
                        true);
                if (addRoutine == null)
                {
                    throw new Exception(
                        "VaM did not provide an Empty creation routine.");
                }
                // From this point onward the fixed UID belongs to this
                // transaction, even if VaM fails part-way through creation.
                result.Created = true;
            }
            catch (Exception exception)
            {
                result.Error =
                    "Could not create the SAM3D camera: " +
                    DescribeException(exception);
                yield break;
            }

            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (true)
            {
                bool hasNext = false;
                object current = null;
                try
                {
                    if (Time.realtimeSinceStartup >= deadline)
                    {
                        throw new Exception(
                            "Empty creation did not finish within 120 seconds.");
                    }
                    hasNext = addRoutine.MoveNext();
                    if (hasNext)
                    {
                        current = addRoutine.Current;
                    }
                }
                catch (Exception exception)
                {
                    result.Error =
                        "Could not create the SAM3D camera: " +
                        DescribeException(exception);
                    yield break;
                }
                if (!hasNext)
                {
                    break;
                }
                yield return current;
            }
            yield return new WaitForEndOfFrame();

            camera =
                SuperController.singleton.GetAtomByUid(
                    request.Sam3dCameraUid);
            if (camera == null || camera.type != "Empty")
            {
                result.Error =
                    "VaM completed creation without the requested Empty.";
                yield break;
            }

            try
            {
                JSONStorable preset =
                    camera.GetStorableByID("Preset");
                JSONStorableUrl browsePath =
                    preset == null
                    ? null
                    : preset.GetUrlJSONParam("presetBrowsePath");
                if (preset == null || browsePath == null)
                {
                    throw new Exception(
                        "The camera Empty does not expose preset loading.");
                }
                JSONStorableBool loadOnSelect =
                    preset.GetBoolJSONParam("loadPresetOnSelect");
                bool previous =
                    loadOnSelect != null && loadOnSelect.val;
                if (loadOnSelect != null)
                {
                    loadOnSelect.val = false;
                }
                try
                {
                    browsePath.val =
                        SuperController.singleton.NormalizePath(
                            Sam3dCameraPreset);
                    preset.CallAction("LoadPreset");
                }
                finally
                {
                    if (loadOnSelect != null)
                    {
                        loadOnSelect.val = previous;
                    }
                }
            }
            catch (Exception exception)
            {
                result.Error =
                    "Could not load the fixed SAM3D camera preset: " +
                    DescribeException(exception);
                yield break;
            }

            LoadingWaitResult loading = new LoadingWaitResult();
            yield return WaitForVaMLoading(
                "SAM3D camera preset loading",
                loading);
            if (loading.Error.Length != 0)
            {
                result.Error = loading.Error;
                yield break;
            }

            deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (FindSam3dRenderer(camera) == null &&
                   Time.realtimeSinceStartup < deadline)
            {
                yield return null;
            }
            if (FindSam3dRenderer(camera) == null)
            {
                result.Error =
                    "The VAM-PIP-enabled VR Video and Funscript Exporter " +
                    "did not become ready within 120 seconds.";
                yield break;
            }
            result.Atom = camera;
        }

        private IEnumerator ExecuteApplySam3dResult(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateApplyingSam3d,
                request.RequestId,
                startedAt,
                "",
                "vam-sam3d",
                "Validating the SAM3D pose and camera solution.");

            Sam3dSolution solution = null;
            Atom person = null;
            string preparationError = "";
            try
            {
                if (CurrentSam3dSnapshot() != null)
                {
                    throw new Exception(
                        "Undo the currently applied SAM3D result before applying another.");
                }
                solution = LoadSam3dSolution(request);
                if (request.Sam3dKeepReference)
                {
                    ValidateSam3dReferenceFile(request);
                }
                person =
                    SuperController.singleton.GetAtomByUid(
                        request.TargetUid);
                if (person == null || person.type != "Person")
                {
                    throw new Exception(
                        "targetUid does not identify an existing Person.");
                }
            }
            catch (Exception exception)
            {
                preparationError =
                    "Could not prepare the SAM3D result: " +
                    DescribeException(exception);
            }
            if (preparationError.Length != 0)
            {
                FinishSam3dActionError(
                    request,
                    startedAt,
                    preparationError);
                yield break;
            }

            Sam3dCameraResult cameraResult =
                new Sam3dCameraResult();
            _inFlightSam3dCameraRequest = request;
            _inFlightSam3dCameraResult = cameraResult;
            yield return EnsureSam3dCamera(request, cameraResult);
            if (cameraResult.Error.Length != 0)
            {
                cameraResult.Error +=
                    RemoveCreatedSam3dCamera(
                        request,
                        cameraResult);
                ClearInFlightSam3dCamera(
                    request,
                    cameraResult);
                FinishSam3dActionError(
                    request,
                    startedAt,
                    cameraResult.Error);
                yield break;
            }

            Sam3dReferenceResult referenceResult =
                new Sam3dReferenceResult();
            if (request.Sam3dKeepReference)
            {
                _inFlightSam3dReferenceRequest = request;
                _inFlightSam3dReferenceResult = referenceResult;
                yield return EnsureSam3dReference(
                    request,
                    referenceResult);
                if (referenceResult.Error.Length != 0)
                {
                    referenceResult.Error +=
                        RemoveCreatedSam3dReference(
                            referenceResult);
                    ClearInFlightSam3dReference(
                        request,
                        referenceResult);
                    referenceResult.Error +=
                        RemoveCreatedSam3dCamera(
                            request,
                            cameraResult);
                    ClearInFlightSam3dCamera(
                        request,
                        cameraResult);
                    FinishSam3dActionError(
                        request,
                        startedAt,
                        referenceResult.Error);
                    yield break;
                }
            }

            Sam3dUndoSnapshot snapshot = null;
            Sam3dReferenceState previousReferenceState =
                CurrentSam3dReferenceState();
            string applyError = "";
            try
            {
                MVRScript renderer =
                    FindSam3dRenderer(cameraResult.Atom);
                if (renderer == null)
                {
                    throw new Exception(
                        "The selected camera has no compatible renderer.");
                }
                Dictionary<string, FreeControllerV3> controllers =
                    Sam3dPersonControllers(person);
                snapshot =
                    SnapshotSam3dState(
                        request,
                        solution,
                        person,
                        cameraResult.Atom,
                        renderer,
                        controllers,
                        request.Sam3dKeepReference
                        ? referenceResult.Atom
                        : null,
                        referenceResult.Created,
                        previousReferenceState);
                snapshot.Diagnostics =
                    NewSam3dApplyDiagnostics(request);
                snapshot.CameraCreated =
                    cameraResult.Created;
                ApplySam3dTransforms(
                    request,
                    solution,
                    person,
                    cameraResult.Atom,
                    renderer,
                    controllers,
                    request.Sam3dKeepReference
                    ? referenceResult.Atom
                    : null,
                    snapshot,
                    snapshot.Diagnostics);
                if (request.Sam3dKeepReference)
                {
                    _sam3dReferenceState =
                        NewSam3dReferenceState(
                            request,
                            referenceResult.Atom,
                            true);
                }
                _sam3dUndoSnapshot = snapshot;
                ClearInFlightSam3dReference(
                    request,
                    referenceResult);
                ClearInFlightSam3dCamera(
                    request,
                    cameraResult);
            }
            catch (Exception exception)
            {
                applyError =
                    "Could not apply the SAM3D result: " +
                    DescribeException(exception);
                if (snapshot != null)
                {
                    try
                    {
                        RestoreSam3dSnapshot(snapshot);
                    }
                    catch (Exception restoreException)
                    {
                        applyError +=
                            " Automatic rollback also failed: " +
                            DescribeException(restoreException);
                    }
                }
                else
                {
                    applyError +=
                        RemoveCreatedSam3dReference(
                            referenceResult);
                }
                applyError +=
                    RemoveCreatedSam3dCamera(
                        request,
                        cameraResult);
                ClearInFlightSam3dReference(
                    request,
                    referenceResult);
                ClearInFlightSam3dCamera(
                    request,
                    cameraResult);
            }
            if (snapshot != null)
            {
                yield return WaitForSam3dPhysicsSettlement();
            }
            if (applyError.Length != 0)
            {
                FinishSam3dActionError(
                    request,
                    startedAt,
                    applyError);
                yield break;
            }

            try
            {
                FinalizeSam3dPersistentHeadLock(snapshot);
            }
            catch (Exception exception)
            {
                applyError =
                    "Could not finalize the settled SAM3D head rotation: " +
                    DescribeException(exception);
                try
                {
                    RestoreSam3dSnapshot(snapshot);
                    _sam3dUndoSnapshot = null;
                }
                catch (Exception restoreException)
                {
                    applyError +=
                        " Automatic rollback also failed: " +
                        DescribeException(restoreException);
                }
                applyError +=
                    RemoveCreatedSam3dCamera(
                        request,
                        cameraResult);
            }
            yield return WaitForSam3dPhysicsSettlement();
            if (applyError.Length != 0)
            {
                FinishSam3dActionError(
                    request,
                    startedAt,
                    applyError);
                yield break;
            }
            try
            {
                CaptureSam3dSettledDiagnostics(
                    snapshot.Diagnostics,
                    Sam3dPersonControllers(person));
            }
            catch (Exception exception)
            {
                snapshot.Diagnostics.Error =
                    DescribeException(exception);
                snapshot.Diagnostics.CapturedAtUtc = UtcNow();
            }

            FinishSam3dActionOk(
                request,
                startedAt,
                "SAM3D pose and VR-and-Funscript camera applied. Undo is available.");
        }

        private IEnumerator ExecuteShowSam3dReference(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateApplyingSam3d,
                request.RequestId,
                startedAt,
                "",
                "vam-sam3d",
                "Placing the SAM3D source image behind the Person.");

            Sam3dSolution solution = null;
            Atom person = null;
            string preparationError = "";
            try
            {
                if (CurrentSam3dSnapshot() != null)
                {
                    throw new Exception(
                        "Undo the currently applied SAM3D pose before changing its reference.");
                }
                solution = LoadSam3dSolution(request);
                ValidateSam3dReferenceFile(request);
                person =
                    SuperController.singleton.GetAtomByUid(
                        request.TargetUid);
                if (person == null ||
                    person.type != "Person")
                {
                    throw new Exception(
                        "targetUid does not identify an existing Person.");
                }
            }
            catch (Exception exception)
            {
                preparationError =
                    "Could not prepare the SAM3D reference: " +
                    DescribeException(exception);
            }
            if (preparationError.Length != 0)
            {
                FinishSam3dActionError(
                    request,
                    startedAt,
                    preparationError);
                yield break;
            }

            Sam3dReferenceResult result =
                new Sam3dReferenceResult();
            _inFlightSam3dReferenceRequest = request;
            _inFlightSam3dReferenceResult = result;
            yield return EnsureSam3dReference(
                request,
                result);
            if (result.Error.Length != 0)
            {
                result.Error +=
                    RemoveCreatedSam3dReference(result);
                ClearInFlightSam3dReference(
                    request,
                    result);
                FinishSam3dActionError(
                    request,
                    startedAt,
                    result.Error);
                yield break;
            }

            Sam3dReferenceState previousState =
                CurrentSam3dReferenceState();
            Sam3dReferenceSnapshot snapshot = null;
            string applyError = "";
            try
            {
                snapshot =
                    SnapshotSam3dReference(
                        result.Atom,
                        result.Created);
                ConfigureSam3dReference(
                    request,
                    solution,
                    person,
                    result.Atom,
                    false);
                _sam3dReferenceState =
                    NewSam3dReferenceState(
                        request,
                        result.Atom,
                        false);
            }
            catch (Exception exception)
            {
                applyError =
                    "Could not show the SAM3D reference: " +
                    DescribeException(exception);
                try
                {
                    if (snapshot != null)
                    {
                        RestoreSam3dReferenceSnapshot(
                            snapshot);
                        _sam3dReferenceState =
                            CloneSam3dReferenceState(
                                previousState);
                    }
                    else
                    {
                        applyError +=
                            RemoveCreatedSam3dReference(
                                result);
                    }
                }
                catch (Exception restoreException)
                {
                    applyError +=
                        " Automatic rollback also failed: " +
                        DescribeException(restoreException);
                }
            }
            ClearInFlightSam3dReference(
                request,
                result);
            if (applyError.Length != 0)
            {
                FinishSam3dActionError(
                    request,
                    startedAt,
                    applyError);
                yield break;
            }

            FinishSam3dActionOk(
                request,
                startedAt,
                "SAM3D source image placed behind the Person.");
        }

        private IEnumerator ExecuteRemoveSam3dReference(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateApplyingSam3d,
                request.RequestId,
                startedAt,
                "",
                "vam-sam3d",
                "Removing the SAM3D reference image.");
            yield return null;

            string removeError = "";
            string message =
                "SAM3D reference was already absent.";
            try
            {
                if (CurrentSam3dSnapshot() != null)
                {
                    throw new Exception(
                        "Undo the currently applied SAM3D pose before removing its reference.");
                }
                Sam3dReferenceState state =
                    CurrentSam3dReferenceState();
                if (state != null &&
                    (!string.Equals(
                        state.JobId,
                        request.Sam3dJobId,
                        StringComparison.OrdinalIgnoreCase) ||
                     !string.Equals(
                        state.JobRevision,
                        request.Sam3dExpectedJobRevision,
                        StringComparison.OrdinalIgnoreCase)))
                {
                    throw new Exception(
                        "The visible reference belongs to another SAM3D job revision.");
                }
                Atom atom =
                    SuperController.singleton.GetAtomByUid(
                        Sam3dReferenceUid);
                if (atom != null)
                {
                    if (atom.type != Sam3dReferenceAtomType)
                    {
                        throw new Exception(
                            "The fixed SAM3D reference UID is not an ImagePanelEmissive.");
                    }
                    string url =
                        RequireSam3dReferenceUrl(atom).val;
                    string expectedPrefix =
                        Sam3dReferencePrefix +
                        request.Sam3dJobId.ToLowerInvariant() +
                        ".";
                    if (!IsOwnedSam3dReferencePath(url) ||
                        !(url ?? "").Replace('\\', '/')
                            .StartsWith(
                                expectedPrefix,
                                StringComparison.Ordinal))
                    {
                        throw new Exception(
                            "The fixed SAM3D reference atom is not owned by this job.");
                    }
                    if (state != null &&
                        !object.ReferenceEquals(
                            atom,
                            state.Atom))
                    {
                        throw new Exception(
                            "The fixed SAM3D reference identity changed.");
                    }
                    SuperController.singleton.RemoveAtom(atom);
                    message =
                        "SAM3D reference removed.";
                }
                _sam3dReferenceState = null;
            }
            catch (Exception exception)
            {
                removeError =
                    "Could not remove the SAM3D reference: " +
                    DescribeException(exception);
            }
            if (removeError.Length != 0)
            {
                FinishSam3dActionError(
                    request,
                    startedAt,
                    removeError);
                yield break;
            }
            FinishSam3dActionOk(
                request,
                startedAt,
                message);
        }

        private IEnumerator ExecuteUndoSam3dResult(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateApplyingSam3d,
                request.RequestId,
                startedAt,
                "",
                "vam-sam3d",
                "Restoring the previous Person and camera state.");
            bool restoreAttempted = false;
            string restoreError = "";
            try
            {
                Sam3dUndoSnapshot snapshot =
                    CurrentSam3dSnapshot();
                if (snapshot == null ||
                    !string.Equals(
                        snapshot.JobId,
                        request.Sam3dJobId,
                        StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(
                        snapshot.Revision,
                        request.Sam3dRevision,
                        StringComparison.OrdinalIgnoreCase))
                {
                    throw new Exception(
                        "No matching in-memory SAM3D undo snapshot is available.");
                }
                restoreAttempted = true;
                RestoreSam3dSnapshot(snapshot);
                _sam3dUndoSnapshot = null;
            }
            catch (Exception exception)
            {
                restoreError =
                    "Could not undo the SAM3D result: " +
                    DescribeException(exception);
            }
            if (restoreAttempted)
            {
                yield return WaitForSam3dPhysicsSettlement();
            }
            if (restoreError.Length != 0)
            {
                FinishSam3dActionError(
                    request,
                    startedAt,
                    restoreError);
                yield break;
            }
            FinishSam3dActionOk(
                request,
                startedAt,
                "Previous Person and camera state restored.");
        }

        private static bool IsSafeSam3dOutput(
            string path,
            string requestId,
            string baseFilename)
        {
            if (path == null)
            {
                return false;
            }
            string normalized = path.Replace('\\', '/');
            const string screenshotPrefix =
                "Saves/screenshots/VAMPip/";
            const string legacyPrefix =
                "Saves/VR_Videos_And_Funscripts/";
            string prefix = "";
            if (normalized.StartsWith(
                    screenshotPrefix,
                    StringComparison.Ordinal))
            {
                prefix = screenshotPrefix;
            }
            else if (normalized.StartsWith(
                         legacyPrefix,
                         StringComparison.Ordinal))
            {
                prefix = legacyPrefix;
            }
            if (prefix.Length == 0 ||
                normalized.IndexOf("..", StringComparison.Ordinal) >= 0)
            {
                return false;
            }
            string expected =
                prefix +
                "vampip_" +
                requestId +
                "_" +
                baseFilename;
            return string.Equals(
                    normalized,
                    expected + ".jpg",
                    StringComparison.OrdinalIgnoreCase) ||
                string.Equals(
                    normalized,
                    expected + ".png",
                    StringComparison.OrdinalIgnoreCase);
        }

        private IEnumerator ExecuteCaptureSam3dResult(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateCapturingSam3d,
                request.RequestId,
                startedAt,
                "",
                "vam-sam3d",
                "Starting the VR-and-Funscript camera capture.");
            Sam3dSolution solution = null;
            MVRScript renderer = null;
            string setupError = "";
            try
            {
                solution = LoadSam3dSolution(request);
                Atom camera =
                    SuperController.singleton.GetAtomByUid(
                        request.Sam3dCameraUid);
                renderer = FindSam3dRenderer(camera);
                if (renderer == null)
                {
                    throw new Exception(
                        "cameraUid does not identify a compatible renderer Empty.");
                }
                Sam3dUndoSnapshot snapshot =
                    CurrentSam3dSnapshot();
                if (snapshot == null ||
                    !string.Equals(
                        snapshot.JobId,
                        request.Sam3dJobId,
                        StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(
                        snapshot.Revision,
                        request.Sam3dRevision,
                        StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(
                        snapshot.CameraUid,
                        request.Sam3dCameraUid,
                        StringComparison.Ordinal) ||
                    !object.ReferenceEquals(
                        snapshot.Renderer,
                        renderer))
                {
                    throw new Exception(
                        "The requested SAM3D pose and camera are not the currently applied in-memory result.");
                }
                ConfigureSam3dRenderer(renderer, solution.Camera);
                JSONStorableString requestId =
                    renderer.GetStringJSONParam(
                        Sam3dRequestIdParam);
                JSONStorableString baseFilename =
                    renderer.GetStringJSONParam(
                        Sam3dBaseFilenameParam);
                JSONStorableAction action =
                    renderer.GetAction(Sam3dCaptureAction);
                if (requestId == null ||
                    baseFilename == null ||
                    action == null ||
                    action.actionCallback == null)
                {
                    throw new Exception(
                        "The renderer's VAM-PIP capture interface is incomplete.");
                }
                requestId.val = request.RequestId;
                baseFilename.val = solution.Camera.BaseFilename;
                action.actionCallback();
            }
            catch (Exception exception)
            {
                setupError =
                    "Could not start the SAM3D capture: " +
                    DescribeException(exception);
            }
            if (setupError.Length != 0)
            {
                FinishSam3dActionError(
                    request,
                    startedAt,
                    setupError);
                yield break;
            }

            float deadline =
                Time.realtimeSinceStartup + Sam3dCaptureWaitSeconds;
            while (Time.realtimeSinceStartup < deadline)
            {
                string state = "";
                string output = "";
                string error = "";
                string pollError = "";
                try
                {
                    if (renderer == null)
                    {
                        throw new Exception(
                            "The capture renderer is no longer available.");
                    }
                    JSONStorableString status =
                        renderer.GetStringJSONParam(
                            Sam3dStatusParam);
                    if (status == null)
                    {
                        throw new Exception(
                            "The renderer's capture status is no longer available.");
                    }
                    state =
                        (status.val ?? "").Trim().ToLowerInvariant();
                    if (state == "succeeded")
                    {
                        JSONStorableString lastOutput =
                            renderer.GetStringJSONParam(
                                Sam3dLastOutputParam);
                        if (lastOutput == null)
                        {
                            throw new Exception(
                                "The renderer's capture output is unavailable.");
                        }
                        output = lastOutput.val;
                    }
                    else if (state == "failed")
                    {
                        JSONStorableString rendererError =
                            renderer.GetStringJSONParam(
                                Sam3dErrorParam);
                        error =
                            rendererError == null
                            ? ""
                            : rendererError.val;
                    }
                }
                catch (Exception exception)
                {
                    pollError =
                        "Could not monitor the SAM3D capture: " +
                        DescribeException(exception);
                }
                if (pollError.Length != 0)
                {
                    FinishSam3dActionError(
                        request,
                        startedAt,
                        pollError);
                    yield break;
                }
                if (state == "succeeded")
                {
                    if (!IsSafeSam3dOutput(
                            output,
                            request.RequestId,
                            solution.Camera.BaseFilename))
                    {
                        FinishSam3dActionError(
                            request,
                            startedAt,
                            "The renderer returned an invalid capture path.");
                        yield break;
                    }
                    FinishSam3dActionOk(
                        request,
                        startedAt,
                        "SAM3D capture saved to " +
                        output.Replace('\\', '/') +
                        ".");
                    yield break;
                }
                if (state == "failed")
                {
                    if (error == null ||
                        error.Trim().Length == 0)
                    {
                        error = "The renderer reported a capture failure.";
                    }
                    if (error.Length > 500)
                    {
                        error = error.Substring(0, 500);
                    }
                    FinishSam3dActionError(
                        request,
                        startedAt,
                        error);
                    yield break;
                }
                yield return null;
            }

            FinishSam3dActionError(
                request,
                startedAt,
                "VR-and-Funscript capture did not finish within 300 seconds.");
        }

        private string PrepareAtomResourceRequest(
            BridgeRequest request,
            string startedAt,
            string actionDescription)
        {
            bool rescanAttempted = false;
            try
            {
                if (request.RescanRequired)
                {
                    rescanAttempted = true;
                    PublishStatus(
                        StateRescanning,
                        request.RequestId,
                        startedAt,
                        "",
                        "",
                        "Rescanning VaM packages before " +
                        actionDescription +
                        ".");
                    SuperController.singleton.RescanPackages();
                }
                if (!FileManagerSecure.FileExists(request.ResourceRef))
                {
                    throw new Exception(
                        "The validated resource does not exist or is not visible to VaM.");
                }
                return "";
            }
            catch (Exception exception)
            {
                return "Could not prepare " +
                    actionDescription +
                    ": " +
                    DescribeException(exception);
            }
            finally
            {
                if (rescanAttempted)
                {
                    _nextAllowedRescanAt =
                        Time.realtimeSinceStartup +
                        MinimumRescanIntervalSeconds;
                }
            }
        }

        private IEnumerator EnsureTargetAtom(
            BridgeRequest request,
            string atomType,
            bool createIfMissing,
            AtomCreationResult result)
        {
            result.Atom = null;
            result.Created = false;
            result.Error = "";

            Atom existing = null;
            IEnumerator addRoutine = null;
            try
            {
                if (SuperController.singleton == null)
                {
                    throw new Exception("VaM's scene controller is unavailable.");
                }
                existing =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (existing == null && createIfMissing)
                {
                    PublishStatus(
                        StateAdding,
                        request.RequestId,
                        "",
                        "",
                        "vam",
                        "Adding " + atomType + " " + request.TargetUid + ".");
                    addRoutine =
                        SuperController.singleton.AddAtomByType(
                            atomType,
                            request.TargetUid,
                            true);
                    if (addRoutine == null)
                    {
                        throw new Exception(
                            "VaM did not provide an atom creation routine.");
                    }
                }
            }
            catch (Exception exception)
            {
                result.Error =
                    "Could not resolve target atom: " +
                    DescribeException(exception);
            }
            if (result.Error.Length != 0)
            {
                yield break;
            }

            if (existing != null)
            {
                if (createIfMissing)
                {
                    result.Error =
                        "createIfMissing requires targetUid to be absent " +
                        "when the request executes.";
                    yield break;
                }
                if (existing.type != atomType)
                {
                    result.Error =
                        "targetUid is already used by an atom of type " +
                        existing.type +
                        ", not " +
                        atomType +
                        ".";
                    yield break;
                }
                result.Atom = existing;
                yield break;
            }
            if (!createIfMissing)
            {
                result.Error =
                    "targetUid does not identify an existing " +
                    atomType +
                    " atom and createIfMissing is false.";
                yield break;
            }

            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (true)
            {
                bool hasNext = false;
                object current = null;
                string iterationError = "";
                if (Time.realtimeSinceStartup >= deadline)
                {
                    iterationError =
                        atomType + " creation did not finish within 120 seconds.";
                }
                else
                {
                    try
                    {
                        hasNext = addRoutine.MoveNext();
                        if (hasNext)
                        {
                            current = addRoutine.Current;
                        }
                    }
                    catch (Exception exception)
                    {
                        iterationError =
                            atomType + " creation failed: " +
                            DescribeException(exception);
                    }
                }
                if (iterationError.Length != 0)
                {
                    result.Error = iterationError;
                    yield break;
                }
                if (!hasNext)
                {
                    break;
                }
                yield return current;
            }

            yield return new WaitForEndOfFrame();
            try
            {
                if (SuperController.singleton == null)
                {
                    throw new Exception(
                        "VaM's scene controller became unavailable.");
                }
                Atom created =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (created == null || created.type != atomType)
                {
                    throw new Exception(
                        "VaM completed creation without the requested " +
                        atomType +
                        " atom.");
                }
                result.Atom = created;
                result.Created = true;
            }
            catch (Exception exception)
            {
                result.Error =
                    "Could not verify the added " +
                    atomType +
                    ": " +
                    DescribeException(exception);
            }
        }

        private IEnumerator WaitForVaMLoading(
            string actionDescription,
            LoadingWaitResult result)
        {
            result.Error = "";

            // Preset and SubScene assignments can raise isLoading
            // asynchronously, so always cross a frame boundary first.
            yield return new WaitForEndOfFrame();

            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (SuperController.singleton != null &&
                   SuperController.singleton.isLoading &&
                   Time.realtimeSinceStartup < deadline)
            {
                yield return null;
            }

            if (SuperController.singleton == null)
            {
                result.Error =
                    "VaM's scene controller became unavailable while " +
                    actionDescription +
                    ".";
            }
            else if (SuperController.singleton.isLoading)
            {
                result.Error =
                    actionDescription +
                    " did not finish within 120 seconds.";
            }
        }

        private IEnumerator ExecuteApplyAtomPreset(BridgeRequest request)
        {
            string startedAt = UtcNow();
            string prepareError =
                PrepareAtomResourceRequest(
                    request,
                    startedAt,
                    "applying the atom preset");
            if (prepareError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, prepareError);
                yield break;
            }

            AtomCreationResult target = new AtomCreationResult();
            yield return EnsureTargetAtom(
                request,
                request.AtomType,
                request.CreateIfMissing,
                target);
            if (target.Error.Length != 0)
            {
                FinishAtomActionError(request, startedAt, target.Error);
                yield break;
            }

            PublishStatus(
                StateApplying,
                request.RequestId,
                startedAt,
                "",
                "vam",
                "Applying " + request.AtomType + " atom preset.");

            string applyError = "";
            try
            {
                JSONStorable presetStorable =
                    target.Atom.GetStorableByID("Preset");
                if (presetStorable == null)
                {
                    throw new Exception(
                        "The target atom does not expose the Preset storable.");
                }
                JSONStorableUrl presetBrowsePath =
                    presetStorable.GetUrlJSONParam("presetBrowsePath");
                if (presetBrowsePath == null)
                {
                    throw new Exception(
                        "The target atom Preset storable has no presetBrowsePath.");
                }

                JSONStorableBool loadPresetOnSelect =
                    presetStorable.GetBoolJSONParam("loadPresetOnSelect");
                bool previousLoadPresetOnSelect = false;
                if (loadPresetOnSelect != null)
                {
                    previousLoadPresetOnSelect = loadPresetOnSelect.val;
                    loadPresetOnSelect.val = false;
                }
                try
                {
                    presetBrowsePath.val =
                        SuperController.singleton.NormalizePath(
                            request.ResourceRef);
                    presetStorable.CallAction(
                        request.Merge
                        ? "MergeLoadPreset"
                        : "LoadPreset");
                }
                finally
                {
                    if (loadPresetOnSelect != null)
                    {
                        loadPresetOnSelect.val = previousLoadPresetOnSelect;
                    }
                }
            }
            catch (Exception exception)
            {
                applyError =
                    "Could not apply atom preset: " +
                    DescribeException(exception);
            }
            if (applyError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, applyError);
                yield break;
            }

            LoadingWaitResult wait = new LoadingWaitResult();
            yield return WaitForVaMLoading("atom preset loading", wait);
            if (wait.Error.Length != 0)
            {
                FinishAtomActionError(request, startedAt, wait.Error);
                yield break;
            }

            FinishAtomActionOk(
                request,
                startedAt,
                request.AtomType +
                (request.Merge ? " atom preset merged." : " atom preset applied."));
        }

        private IEnumerator ExecuteLoadSubscene(BridgeRequest request)
        {
            string startedAt = UtcNow();
            string prepareError =
                PrepareAtomResourceRequest(
                    request,
                    startedAt,
                    "loading the SubScene");
            if (prepareError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, prepareError);
                yield break;
            }

            AtomCreationResult target = new AtomCreationResult();
            yield return EnsureTargetAtom(
                request,
                "SubScene",
                request.CreateIfMissing,
                target);
            if (target.Error.Length != 0)
            {
                FinishAtomActionError(request, startedAt, target.Error);
                yield break;
            }

            PublishStatus(
                StateApplying,
                request.RequestId,
                startedAt,
                "",
                "vam",
                "Loading SubScene.");

            string loadError = "";
            try
            {
                JSONStorable subsceneStorable =
                    target.Atom.GetStorableByID("SubScene");
                if (subsceneStorable == null)
                {
                    throw new Exception(
                        "The target atom does not expose the SubScene storable.");
                }
                JSONStorableUrl browsePath =
                    subsceneStorable.GetUrlJSONParam("browsePath");
                if (browsePath == null)
                {
                    throw new Exception(
                        "The target SubScene storable has no browsePath.");
                }
                browsePath.val =
                    SuperController.singleton.NormalizePath(
                        request.ResourceRef);
            }
            catch (Exception exception)
            {
                loadError =
                    "Could not load SubScene: " +
                    DescribeException(exception);
            }
            if (loadError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, loadError);
                yield break;
            }

            LoadingWaitResult wait = new LoadingWaitResult();
            yield return WaitForVaMLoading("SubScene loading", wait);
            if (wait.Error.Length != 0)
            {
                FinishAtomActionError(request, startedAt, wait.Error);
                yield break;
            }

            FinishAtomActionOk(request, startedAt, "SubScene loaded.");
        }

        private static void ResolveCuaLoader(
            Atom atom,
            CuaLoaderState state)
        {
            state.Loader = null;
            state.AssetUrl = null;
            state.AssetName = null;
            state.LoadDll = null;
            state.Error = "";
            if (atom == null || atom.type != "CustomUnityAsset")
            {
                state.Error =
                    "targetUid does not identify a CustomUnityAsset atom.";
                return;
            }
            state.Loader =
                atom.GetStorableByID("asset") as CustomUnityAssetLoader;
            if (state.Loader == null)
            {
                state.Error =
                    "The target CustomUnityAsset has no native asset loader.";
                return;
            }
            state.AssetUrl = state.Loader.GetUrlJSONParam("assetUrl");
            state.AssetName =
                state.Loader.GetStringChooserJSONParam("assetName");
            state.LoadDll = state.Loader.GetBoolJSONParam("loadDll");
            if (state.AssetUrl == null ||
                state.AssetName == null ||
                state.LoadDll == null)
            {
                state.Error =
                    "The target CustomUnityAsset loader is missing a required " +
                    "assetUrl, assetName, or loadDll parameter.";
            }
        }

        private static bool IsEligibleCuaChoice(string choice)
        {
            return choice != null &&
                choice.Trim().Length != 0 &&
                !choice.Trim().Equals(
                    "None",
                    StringComparison.OrdinalIgnoreCase) &&
                SanitizeCuaChoiceLabel(choice).Length != 0;
        }

        private static string GetCuaNoneChoice(
            JSONStorableStringChooser assetName)
        {
            if (assetName != null && assetName.choices != null)
            {
                int index;
                for (index = 0; index < assetName.choices.Count; index++)
                {
                    string choice = assetName.choices[index];
                    if (choice != null &&
                        choice.Trim().Equals(
                            "None",
                            StringComparison.OrdinalIgnoreCase))
                    {
                        return choice;
                    }
                }
            }
            return "None";
        }

        private static List<int> GetEligibleCuaChoiceIndices(
            JSONStorableStringChooser assetName)
        {
            List<int> result = new List<int>();
            if (assetName == null || assetName.choices == null)
            {
                return result;
            }
            int index;
            for (index = 0; index < assetName.choices.Count; index++)
            {
                if (IsEligibleCuaChoice(assetName.choices[index]))
                {
                    result.Add(index);
                }
            }
            return result;
        }

        private static void AbortUnsafeCuaLoad(CuaLoaderState state)
        {
            if (state == null || state.LoadDll == null)
            {
                return;
            }
            try
            {
                state.LoadDll.val = false;
                if (state.AssetName != null)
                {
                    state.AssetName.val = GetCuaNoneChoice(state.AssetName);
                }
                state.LoadDll.val = false;
                if (state.AssetUrl != null)
                {
                    state.AssetUrl.val = "";
                }
                state.LoadDll.val = false;
            }
            catch
            {
                // This is a best-effort abort after the safety invariant was
                // violated. The failure status still tells the caller that
                // the target must be inspected before another load.
            }
        }

        private static string ValidateLiveCuaOperation(
            BridgeRequest request,
            Atom expectedAtom,
            CustomUnityAssetLoader expectedLoader,
            string expectedUrl,
            CuaLoaderState state)
        {
            if (SuperController.singleton == null)
            {
                return "VaM's scene controller became unavailable.";
            }
            Atom current =
                SuperController.singleton.GetAtomByUid(request.TargetUid);
            if (current == null ||
                current.type != "CustomUnityAsset" ||
                !object.ReferenceEquals(current, expectedAtom))
            {
                return "The CustomUnityAsset target changed while loading.";
            }
            ResolveCuaLoader(current, state);
            if (state.Error.Length != 0)
            {
                return state.Error;
            }
            if (!object.ReferenceEquals(state.Loader, expectedLoader))
            {
                return "The CustomUnityAsset loader changed while loading.";
            }
            if (state.LoadDll.val)
            {
                AbortUnsafeCuaLoad(state);
                return "The CUA load was aborted because loadDll became enabled.";
            }
            if (expectedUrl != null &&
                !string.Equals(
                    state.AssetUrl.val,
                    expectedUrl,
                    StringComparison.Ordinal))
            {
                return "The CustomUnityAsset bundle changed while loading.";
            }
            return "";
        }

        private bool IsCurrentCuaChoiceSnapshot(
            string targetUid,
            CuaChoiceSnapshot expected,
            string choiceToken,
            List<string> currentChoices)
        {
            CuaChoiceSnapshot current = null;
            return expected != null &&
                _cuaChoiceSnapshots.TryGetValue(targetUid, out current) &&
                object.ReferenceEquals(current, expected) &&
                object.ReferenceEquals(current.ChoiceList, currentChoices) &&
                string.Equals(
                    current.ChoiceToken,
                    choiceToken,
                    StringComparison.OrdinalIgnoreCase);
        }

        private IEnumerator ExecuteLoadCustomUnityAsset(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            string prepareError =
                PrepareAtomResourceRequest(
                    request,
                    startedAt,
                    "loading the Custom Unity Asset");
            if (prepareError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, prepareError);
                yield break;
            }

            AtomCreationResult target = new AtomCreationResult();
            yield return EnsureTargetAtom(
                request,
                "CustomUnityAsset",
                request.CreateIfMissing,
                target);
            if (target.Error.Length != 0)
            {
                FinishAtomActionError(request, startedAt, target.Error);
                yield break;
            }

            PublishStatus(
                StateApplying,
                request.RequestId,
                startedAt,
                "",
                "vam",
                "Loading Custom Unity Asset bundle with DLL loading disabled.");

            CuaLoaderState state = new CuaLoaderState();
            string normalizedUrl = "";
            string startError = "";
            try
            {
                ResolveCuaLoader(target.Atom, state);
                if (state.Error.Length != 0)
                {
                    throw new Exception(state.Error);
                }

                normalizedUrl =
                    SuperController.singleton.NormalizePath(
                        request.ResourceRef);
                state.AssetName.val = GetCuaNoneChoice(state.AssetName);

                // VaM samples loadDll synchronously from the assetUrl callback.
                // Keep these statements adjacent: changing loadDll afterwards
                // cannot unload an assembly that already executed.
                state.LoadDll.val = false;
                if (state.LoadDll.val)
                {
                    throw new Exception(
                        "The target refused to disable loadDll.");
                }
                state.AssetUrl.val = normalizedUrl;
            }
            catch (Exception exception)
            {
                startError =
                    "Could not start Custom Unity Asset loading: " +
                    DescribeException(exception);
            }
            if (startError.Length != 0)
            {
                if (state.LoadDll != null && state.LoadDll.val)
                {
                    AbortUnsafeCuaLoad(state);
                }
                FinishAtomActionError(request, startedAt, startError);
                yield break;
            }

            // A concurrent native loader rejects the new URL and restores its
            // in-flight value. Cross a frame and verify what the storable kept.
            yield return new WaitForEndOfFrame();

            string liveError =
                ValidateLiveCuaOperation(
                    request,
                    target.Atom,
                    state.Loader,
                    normalizedUrl,
                    state);
            if (liveError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, liveError);
                yield break;
            }

            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            List<int> eligible = GetEligibleCuaChoiceIndices(state.AssetName);
            while (eligible.Count == 0 &&
                   Time.realtimeSinceStartup < deadline)
            {
                yield return null;
                liveError =
                    ValidateLiveCuaOperation(
                        request,
                        target.Atom,
                        state.Loader,
                        normalizedUrl,
                        state);
                if (liveError.Length != 0)
                {
                    FinishAtomActionError(request, startedAt, liveError);
                    yield break;
                }
                eligible = GetEligibleCuaChoiceIndices(state.AssetName);
            }
            if (eligible.Count == 0)
            {
                FinishAtomActionError(
                    request,
                    startedAt,
                    "The bundle exposed no scene or prefab choice within 120 seconds.");
                yield break;
            }

            if (eligible.Count > 1)
            {
                FinishAtomActionOk(
                    request,
                    startedAt,
                    "Custom Unity Asset bundle is ready; choose one contained " +
                    "scene or prefab from the picker.");
                yield break;
            }

            int selectedIndex = eligible[0];
            string selectedChoice = state.AssetName.choices[selectedIndex];
            string selectionError = "";
            try
            {
                state.AssetName.val = selectedChoice;
            }
            catch (Exception exception)
            {
                selectionError =
                    "Could not select the bundle's only asset: " +
                    DescribeException(exception);
            }
            if (selectionError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, selectionError);
                yield break;
            }

            yield return new WaitForEndOfFrame();
            while (!state.Loader.isAssetLoaded &&
                   Time.realtimeSinceStartup < deadline)
            {
                liveError =
                    ValidateLiveCuaOperation(
                        request,
                        target.Atom,
                        state.Loader,
                        normalizedUrl,
                        state);
                if (liveError.Length != 0)
                {
                    FinishAtomActionError(request, startedAt, liveError);
                    yield break;
                }
                yield return null;
            }

            liveError =
                ValidateLiveCuaOperation(
                    request,
                    target.Atom,
                    state.Loader,
                    normalizedUrl,
                    state);
            if (liveError.Length == 0 &&
                (!state.Loader.isAssetLoaded ||
                 !string.Equals(
                     state.AssetName.val,
                     selectedChoice,
                     StringComparison.Ordinal)))
            {
                liveError =
                    "The contained asset did not finish loading within 120 seconds.";
            }
            if (liveError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, liveError);
                yield break;
            }

            FinishAtomActionOk(
                request,
                startedAt,
                "Custom Unity Asset bundle and its only contained asset loaded.");
        }

        private IEnumerator ExecuteSelectCustomUnityAssetChoice(
            BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateApplying,
                request.RequestId,
                startedAt,
                "",
                "vam",
                "Selecting a published Custom Unity Asset choice.");

            Atom target = null;
            CuaLoaderState state = new CuaLoaderState();
            CuaChoiceSnapshot snapshot = null;
            string selectedChoice = "";
            string selectedUrl = "";
            string validationError = "";
            try
            {
                target =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (target == null || target.type != "CustomUnityAsset")
                {
                    throw new Exception(
                        "targetUid does not identify a CustomUnityAsset atom.");
                }
                ResolveCuaLoader(target, state);
                if (state.Error.Length != 0)
                {
                    throw new Exception(state.Error);
                }
                if (state.LoadDll.val)
                {
                    throw new Exception(
                        "The target has loadDll enabled; disable it before " +
                        "selecting an asset.");
                }
                if (!_cuaChoiceSnapshots.TryGetValue(
                        request.TargetUid,
                        out snapshot) ||
                    !object.ReferenceEquals(snapshot.Atom, target) ||
                    !object.ReferenceEquals(snapshot.Loader, state.Loader) ||
                    !object.ReferenceEquals(
                        snapshot.ChoiceList,
                        state.AssetName.choices) ||
                    !string.Equals(
                        snapshot.ChoiceToken,
                        request.ChoiceToken,
                        StringComparison.OrdinalIgnoreCase))
                {
                    throw new Exception(
                        "The CUA choice token is stale; refresh the live roster.");
                }
                string currentGeneration =
                    BuildCuaGenerationKey(
                        state.AssetUrl,
                        state.AssetName,
                        snapshot.PublishedIndices);
                if (!string.Equals(
                        snapshot.GenerationKey,
                        currentGeneration,
                        StringComparison.Ordinal))
                {
                    throw new Exception(
                        "The CUA bundle choices changed; refresh the live roster.");
                }
                if (!snapshot.PublishedIndices.Contains(request.ChoiceIndex) ||
                    state.AssetName.choices == null ||
                    request.ChoiceIndex >= state.AssetName.choices.Count ||
                    !IsEligibleCuaChoice(
                        state.AssetName.choices[request.ChoiceIndex]))
                {
                    throw new Exception(
                        "choiceIndex was not present in the published CUA choices.");
                }
                selectedChoice =
                    state.AssetName.choices[request.ChoiceIndex];
                selectedUrl = state.AssetUrl.val;
                state.AssetName.val = selectedChoice;
            }
            catch (Exception exception)
            {
                validationError =
                    "Could not select Custom Unity Asset choice: " +
                    DescribeException(exception);
            }
            if (validationError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, validationError);
                yield break;
            }

            yield return new WaitForEndOfFrame();
            float deadline =
                Time.realtimeSinceStartup + MaximumOperationWaitSeconds;
            while (!state.Loader.isAssetLoaded &&
                   Time.realtimeSinceStartup < deadline)
            {
                CuaLoaderState currentState = new CuaLoaderState();
                string liveError =
                    ValidateLiveCuaOperation(
                        request,
                        target,
                        state.Loader,
                        selectedUrl,
                        currentState);
                if (liveError.Length == 0)
                {
                    if (!IsCurrentCuaChoiceSnapshot(
                            request.TargetUid,
                            snapshot,
                            request.ChoiceToken,
                            currentState.AssetName.choices))
                    {
                        liveError =
                            "The CUA choice token became stale while selecting.";
                    }
                }
                if (liveError.Length == 0)
                {
                    string currentGeneration =
                        BuildCuaGenerationKey(
                            currentState.AssetUrl,
                            currentState.AssetName,
                            snapshot.PublishedIndices);
                    if (!string.Equals(
                            snapshot.GenerationKey,
                            currentGeneration,
                            StringComparison.Ordinal))
                    {
                        liveError =
                            "The CUA bundle choices changed while selecting.";
                    }
                }
                if (liveError.Length != 0)
                {
                    FinishAtomActionError(request, startedAt, liveError);
                    yield break;
                }
                yield return null;
            }

            string finishError = "";
            CuaLoaderState finalState = new CuaLoaderState();
            finishError =
                ValidateLiveCuaOperation(
                    request,
                    target,
                    state.Loader,
                    selectedUrl,
                    finalState);
            if (finishError.Length == 0)
            {
                if (!IsCurrentCuaChoiceSnapshot(
                        request.TargetUid,
                        snapshot,
                        request.ChoiceToken,
                        finalState.AssetName.choices))
                {
                    finishError =
                        "The CUA choice token became stale while selecting.";
                }
            }
            if (finishError.Length == 0)
            {
                string currentGeneration =
                    BuildCuaGenerationKey(
                        finalState.AssetUrl,
                        finalState.AssetName,
                        snapshot.PublishedIndices);
                if (!string.Equals(
                        snapshot.GenerationKey,
                        currentGeneration,
                        StringComparison.Ordinal))
                {
                    finishError =
                        "The CUA bundle choices changed while selecting.";
                }
                else if (!finalState.Loader.isAssetLoaded ||
                         !string.Equals(
                             finalState.AssetName.val,
                             selectedChoice,
                             StringComparison.Ordinal))
                {
                    finishError =
                        "The selected CUA asset did not finish loading within " +
                        "120 seconds.";
                }
            }
            if (finishError.Length != 0)
            {
                FinishAtomActionError(request, startedAt, finishError);
                yield break;
            }

            FinishAtomActionOk(
                request,
                startedAt,
                "Custom Unity Asset choice loaded.");
        }

        private TimelineSnapshot FindTimelineSnapshot(string timelineId)
        {
            foreach (
                KeyValuePair<string, TimelineSnapshot> entry
                in _timelineSnapshots)
            {
                TimelineSnapshot snapshot = entry.Value;
                if (snapshot != null &&
                    string.Equals(
                        snapshot.TimelineId,
                        timelineId,
                        StringComparison.OrdinalIgnoreCase))
                {
                    return snapshot;
                }
            }
            return null;
        }

        private static TimelineItemSnapshot FindTimelineItem(
            List<TimelineItemSnapshot> items,
            string token)
        {
            if (items == null)
            {
                return null;
            }
            int index;
            for (index = 0; index < items.Count; index++)
            {
                TimelineItemSnapshot item = items[index];
                if (item != null &&
                    string.Equals(
                        item.Token,
                        token,
                        StringComparison.OrdinalIgnoreCase))
                {
                    return item;
                }
            }
            return null;
        }

        private void ExecuteTimelineControl(BridgeRequest request)
        {
            string startedAt = UtcNow();
            PublishStatus(
                StateApplying,
                request.RequestId,
                startedAt,
                "",
                "",
                "Applying an allowlisted Timeline control.");
            try
            {
                TimelineSnapshot snapshot =
                    FindTimelineSnapshot(request.TimelineId);
                if (snapshot == null ||
                    snapshot.Atom == null ||
                    snapshot.Plugin == null)
                {
                    throw new Exception(
                        "Timeline instance is no longer available.");
                }
                if (!string.Equals(
                        snapshot.Revision,
                        request.TimelineRevision,
                        StringComparison.OrdinalIgnoreCase))
                {
                    throw new Exception(
                        "Timeline catalog changed; refresh before controlling it.");
                }
                JSONStorable live =
                    snapshot.Atom.GetStorableByID(snapshot.StorableId);
                if (!object.ReferenceEquals(live, snapshot.Plugin))
                {
                    throw new Exception(
                        "Timeline plugin instance changed; refresh the roster.");
                }

                if (snapshot.Enhanced)
                {
                    ExecuteEnhancedTimelineControl(snapshot, request);
                }
                else
                {
                    ExecuteBasicTimelineControl(snapshot, request);
                }

                CompleteRequest(request.RequestId);
                PublishTimelineStatus();
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    snapshot.Enhanced
                    ? "timeline-adapter-v1"
                    : "timeline-storables",
                    "Timeline control applied.");
            }
            catch (Exception exception)
            {
                FailRequest(
                    request,
                    startedAt,
                    "Could not control Timeline: " +
                    DescribeException(exception));
            }
        }

        private static void ExecuteEnhancedTimelineControl(
            TimelineSnapshot snapshot,
            BridgeRequest request)
        {
            JSONStorableString commandParam =
                snapshot.Plugin.GetStringJSONParam(
                    TimelineExternalCommand);
            JSONStorableString resultParam =
                snapshot.Plugin.GetStringJSONParam(
                    TimelineExternalResult);
            JSONStorableAction execute =
                snapshot.Plugin.GetAction(
                    TimelineExecuteExternalCommand);
            if (commandParam == null ||
                resultParam == null ||
                execute == null ||
                execute.actionCallback == null)
            {
                throw new Exception(
                    "Timeline external adapter controls are unavailable.");
            }

            JSONClass command = new JSONClass();
            command["protocol"].AsInt = TimelineProtocolVersion;
            command["requestId"] = request.RequestId;
            command["expectedCatalogRevision"].AsInt =
                snapshot.CatalogRevision;
            command["op"] = request.TimelineOperation;

            TimelineItemSnapshot item = null;
            if (request.TimelineOperation == "selectClip" ||
                request.TimelineOperation == "playClip")
            {
                item = FindTimelineItem(
                    snapshot.Clips,
                    request.TimelineItemToken);
                if (item == null)
                {
                    throw new Exception(
                        "Clip ID was not published for this revision.");
                }
                command["clipId"].AsInt = item.AdapterId;
            }
            else if (request.TimelineOperation == "selectSegment")
            {
                item = FindTimelineItem(
                    snapshot.Segments,
                    request.TimelineItemToken);
                if (item == null)
                {
                    throw new Exception(
                        "Segment ID was not published for this revision.");
                }
                command["segmentId"].AsInt = item.AdapterId;
            }
            else if (request.TimelineOperation == "selectLayer")
            {
                item = FindTimelineItem(
                    snapshot.Layers,
                    request.TimelineItemToken);
                if (item == null)
                {
                    throw new Exception(
                        "Layer ID was not published for this revision.");
                }
                command["layerId"].AsInt = item.AdapterId;
            }
            else if (request.TimelineOperation == "setLocked")
            {
                command["value"].AsBool =
                    request.TimelineBoolValue;
            }
            else if (
                request.TimelineOperation == "setTime" ||
                request.TimelineOperation == "setSpeed" ||
                request.TimelineOperation == "setWeight")
            {
                command["value"].AsFloat =
                    request.TimelineNumberValue;
            }

            commandParam.val = command.ToString();
            execute.actionCallback();

            JSONClass result =
                JSON.Parse(resultParam.val ?? "").AsObject;
            if (result == null ||
                result["protocol"].AsInt != TimelineProtocolVersion ||
                !string.Equals(
                    ((string)result["requestId"] ?? "").Trim(),
                    request.RequestId,
                    StringComparison.Ordinal))
            {
                throw new Exception(
                    "Timeline adapter returned no matching result.");
            }
            if (!result["ok"].AsBool)
            {
                string code = SanitizeTimelineText(
                    (string)result["code"],
                    64);
                string message = SanitizeTimelineText(
                    (string)result["message"],
                    500);
                throw new Exception(
                    "Timeline adapter rejected the command" +
                    (code.Length == 0 ? "" : " (" + code + ")") +
                    (message.Length == 0 ? "." : ": " + message));
            }
        }

        private static void InvokeTimelineAction(
            MVRScript plugin,
            string actionName)
        {
            if (actionName != "Play If Not Playing" &&
                actionName != "Stop If Playing" &&
                actionName != "Stop And Reset" &&
                actionName != "Next Frame" &&
                actionName != "Previous Frame" &&
                actionName != "Play Current Clip")
            {
                throw new Exception(
                    "Timeline action is not allowlisted.");
            }
            JSONStorableAction action = plugin.GetAction(actionName);
            if (action == null || action.actionCallback == null)
            {
                throw new Exception(
                    "Timeline does not provide the requested control.");
            }
            action.actionCallback();
        }

        private static void ExecuteBasicTimelineControl(
            TimelineSnapshot snapshot,
            BridgeRequest request)
        {
            MVRScript plugin = snapshot.Plugin;
            string operation = request.TimelineOperation;
            if (operation == "play")
            {
                JSONStorableBool paused =
                    plugin.GetBoolJSONParam("Paused");
                if (paused != null)
                {
                    paused.val = false;
                }
                InvokeTimelineAction(plugin, "Play If Not Playing");
                return;
            }
            if (operation == "pause")
            {
                JSONStorableBool paused =
                    plugin.GetBoolJSONParam("Paused");
                if (paused == null)
                {
                    throw new Exception(
                        "Timeline pause control is unavailable.");
                }
                paused.val = true;
                return;
            }
            if (operation == "stop")
            {
                InvokeTimelineAction(plugin, "Stop If Playing");
                return;
            }
            if (operation == "reset")
            {
                InvokeTimelineAction(plugin, "Stop And Reset");
                return;
            }
            if (operation == "nextFrame")
            {
                InvokeTimelineAction(plugin, "Next Frame");
                return;
            }
            if (operation == "previousFrame")
            {
                InvokeTimelineAction(plugin, "Previous Frame");
                return;
            }
            if (operation == "selectClip" || operation == "playClip")
            {
                TimelineItemSnapshot item =
                    FindTimelineItem(
                        snapshot.Clips,
                        request.TimelineItemToken);
                JSONStorableStringChooser chooser =
                    plugin.GetStringChooserJSONParam("Animation");
                if (item == null ||
                    chooser == null ||
                    chooser.choices == null ||
                    item.AdapterId < 0 ||
                    item.AdapterId >= chooser.choices.Count ||
                    !string.Equals(
                        chooser.choices[item.AdapterId],
                        item.RawName,
                        StringComparison.Ordinal))
                {
                    throw new Exception(
                        "Timeline clip list changed; refresh the roster.");
                }
                chooser.val = item.RawName;
                if (operation == "playClip")
                {
                    InvokeTimelineAction(plugin, "Play Current Clip");
                }
                return;
            }
            if (operation == "selectSegment" ||
                operation == "selectLayer")
            {
                throw new Exception(
                    "This Timeline version needs the VAM-PIP adapter " +
                    "for segment and layer selection.");
            }
            if (operation == "setTime")
            {
                JSONStorableFloat parameter =
                    plugin.GetFloatJSONParam("Set Time");
                if (parameter == null)
                {
                    throw new Exception(
                        "Timeline time control is unavailable.");
                }
                parameter.val = request.TimelineNumberValue;
                return;
            }
            if (operation == "setSpeed")
            {
                JSONStorableFloat parameter =
                    plugin.GetFloatJSONParam("Speed");
                if (parameter == null)
                {
                    throw new Exception(
                        "Timeline speed control is unavailable.");
                }
                parameter.val = request.TimelineNumberValue;
                return;
            }
            if (operation == "setWeight")
            {
                JSONStorableFloat parameter =
                    plugin.GetFloatJSONParam("Weight");
                if (parameter == null)
                {
                    throw new Exception(
                        "Timeline weight control is unavailable.");
                }
                parameter.val = request.TimelineNumberValue;
                return;
            }
            if (operation == "setLocked")
            {
                JSONStorableBool parameter =
                    plugin.GetBoolJSONParam("Locked");
                if (parameter == null)
                {
                    throw new Exception(
                        "Timeline lock control is unavailable.");
                }
                parameter.val = request.TimelineBoolValue;
                return;
            }
            throw new Exception("Unsupported Timeline control.");
        }

        private void ExecuteSelectAtom(
            BridgeRequest request,
            bool requirePerson)
        {
            string startedAt = UtcNow();
            string targetDescription =
                requirePerson ? "Person" : "atom";
            PublishStatus(
                StateSelecting,
                request.RequestId,
                startedAt,
                "",
                "",
                "Selecting " +
                targetDescription +
                " " +
                request.TargetUid +
                ".");
            try
            {
                Atom atom =
                    SuperController.singleton.GetAtomByUid(request.TargetUid);
                if (atom == null)
                {
                    throw new Exception(
                        "targetUid does not identify an atom in the current scene.");
                }
                if (requirePerson && atom.type != "Person")
                {
                    throw new Exception(
                        "targetUid does not identify a Person atom in the current scene.");
                }
                if (atom.mainController == null)
                {
                    throw new Exception(
                        "The target " +
                        targetDescription +
                        " has no main controller.");
                }

                Atom selected = SuperController.singleton.GetSelectedAtom();
                if (selected == null || selected.uid != atom.uid)
                {
                    SuperController.singleton.SelectController(
                        atom.mainController,
                        false,
                        false,
                        true);
                }
                CompleteRequest(request.RequestId);
                PublishSceneStatus();
                PublishStatus(
                    StateOk,
                    request.RequestId,
                    startedAt,
                    UtcNow(),
                    "vam",
                    requirePerson
                    ? "Person selected."
                    : "Atom selected.");
                SuperController.LogMessage(
                    "[VAM-PIP Bridge] Selected " +
                    targetDescription +
                    " " +
                    request.TargetUid +
                    ".");
            }
            catch (Exception exception)
            {
                FailRequest(
                    request,
                    startedAt,
                    "Could not select " +
                    targetDescription +
                    ": " +
                    DescribeException(exception));
            }
        }

        private void FailRequest(
            BridgeRequest request,
            string startedAt,
            string message)
        {
            _lastHandledRequestId = request.RequestId;
            PublishStatus(
                StateError,
                request.RequestId,
                startedAt,
                UtcNow(),
                "",
                message);
            SuperController.LogError("[VAM-PIP Bridge] " + message);
        }

        private void CompleteRequest(string requestId)
        {
            _lastHandledRequestId = requestId;
            _lastCompletedRequestId = requestId;
        }

        private static string SanitizeCuaChoiceLabel(string value)
        {
            if (value == null)
            {
                return "";
            }
            char[] characters = value.ToCharArray();
            int index;
            for (index = 0; index < characters.Length; index++)
            {
                if (characters[index] < ' ' || characters[index] == '\u007f')
                {
                    characters[index] = ' ';
                }
            }
            string result = new string(characters).Trim();
            if (result.Length > MaximumCuaChoiceLabelLength)
            {
                result = result.Substring(0, MaximumCuaChoiceLabelLength);
            }
            return result;
        }

        private static void HashCuaText(
            ref ulong first,
            ref ulong second,
            string value)
        {
            unchecked
            {
                if (value == null)
                {
                    first = (first ^ 0xffffffffUL) * 1099511628211UL;
                    second = (second ^ 0xfffffffeUL) * 14029467366897019727UL;
                    return;
                }
                first = (first ^ (ulong)value.Length) * 1099511628211UL;
                second =
                    (second ^ ((ulong)value.Length + 0x9e3779b97f4a7c15UL)) *
                    14029467366897019727UL;
                int index;
                for (index = 0; index < value.Length; index++)
                {
                    ulong character = value[index];
                    first = (first ^ character) * 1099511628211UL;
                    second =
                        (second ^ (character + 0x517cc1b727220a95UL)) *
                        14029467366897019727UL;
                }
                first = (first ^ 0xffUL) * 1099511628211UL;
                second = (second ^ 0xfeUL) * 14029467366897019727UL;
            }
        }

        private static string BuildCuaGenerationKey(
            JSONStorableUrl assetUrl,
            JSONStorableStringChooser assetName,
            List<int> publishedIndices)
        {
            ulong first = 1469598103934665603UL;
            ulong second = 7809847782465536322UL;
            HashCuaText(
                ref first,
                ref second,
                assetUrl == null ? null : assetUrl.val);

            List<string> choices =
                assetName == null ? null : assetName.choices;
            HashCuaText(
                ref first,
                ref second,
                choices == null ? "-1" : choices.Count.ToString());

            int publishedCount =
                publishedIndices == null ? 0 : publishedIndices.Count;
            HashCuaText(
                ref first,
                ref second,
                publishedCount.ToString());
            if (publishedIndices != null)
            {
                int publishedOffset;
                for (publishedOffset = 0;
                     publishedOffset < publishedIndices.Count;
                     publishedOffset++)
                {
                    int originalIndex = publishedIndices[publishedOffset];
                    HashCuaText(
                        ref first,
                        ref second,
                        originalIndex.ToString());
                    string raw =
                        choices != null &&
                        originalIndex >= 0 &&
                        originalIndex < choices.Count
                        ? choices[originalIndex]
                        : null;
                    HashCuaText(
                        ref first,
                        ref second,
                        raw);
                }
            }
            return first.ToString("x16") + second.ToString("x16");
        }

        private static int CompareActiveClothingEntries(
            ActiveClothingEntry left,
            ActiveClothingEntry right)
        {
            int resourceOrder = string.Compare(
                left == null ? "" : left.ResourceRef,
                right == null ? "" : right.ResourceRef,
                StringComparison.OrdinalIgnoreCase);
            if (resourceOrder != 0)
            {
                return resourceOrder;
            }
            int packageOrder = string.Compare(
                left == null ? "" : left.PackageUid,
                right == null ? "" : right.PackageUid,
                StringComparison.Ordinal);
            if (packageOrder != 0)
            {
                return packageOrder;
            }
            return string.Compare(
                left == null ? "" : left.InternalUid,
                right == null ? "" : right.InternalUid,
                StringComparison.Ordinal);
        }

        private static string SanitizeRosterText(
            string value,
            int maximumLength)
        {
            if (value == null)
            {
                return "";
            }
            char[] characters = value.ToCharArray();
            int index;
            for (index = 0; index < characters.Length; index++)
            {
                if (characters[index] < ' ' || characters[index] == '\u007f')
                {
                    characters[index] = ' ';
                }
            }
            string result = new string(characters).Trim();
            if (result.Length > maximumLength)
            {
                result = result.Substring(0, maximumLength);
            }
            return result;
        }

        private static string[] SanitizeRosterTags(string[] values)
        {
            List<string> result = new List<string>();
            HashSet<string> seen =
                new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            if (values == null)
            {
                return result.ToArray();
            }
            int index;
            for (index = 0;
                 index < values.Length &&
                 result.Count < MaximumRosterTagsPerItem;
                 index++)
            {
                string tag = SanitizeRosterText(
                    values[index],
                    MaximumRosterTagLength);
                if (tag.Length == 0 || !seen.Add(tag))
                {
                    continue;
                }
                result.Add(tag);
            }
            return result.ToArray();
        }

        private static JSONArray BuildRosterTags(string[] tags)
        {
            JSONArray result = new JSONArray();
            if (tags == null)
            {
                return result;
            }
            int index;
            for (index = 0; index < tags.Length; index++)
            {
                result.Add(tags[index]);
            }
            return result;
        }

        private static List<ActiveClothingEntry> GetActiveClothingEntries(
            Atom atom,
            DAZCharacterSelector geometry)
        {
            List<ActiveClothingEntry> result =
                new List<ActiveClothingEntry>();
            if (atom == null || geometry == null || atom.type != "Person")
            {
                return result;
            }
            DAZClothingItem[] items =
                atom.GetComponentsInChildren<DAZClothingItem>();
            if (items == null)
            {
                return result;
            }
            int index;
            for (index = 0; index < items.Length; index++)
            {
                DAZClothingItem item = items[index];
                if (item == null || !item.active)
                {
                    continue;
                }
                string rawResourceRef =
                    item.dynamicRuntimeLoadPath ?? "";
                if (rawResourceRef.Length == 0)
                {
                    // VaM serializes the exact clothing resource as the item
                    // id. Built-in items also use uid, but they fail the
                    // scoped resource validation below and remain private.
                    rawResourceRef = item.uid ?? "";
                }
                string resourceRef = "";
                if (rawResourceRef.Length != 0)
                {
                    try
                    {
                        resourceRef =
                            FileManagerSecure.NormalizePath(rawResourceRef);
                        string prefix =
                            GetClothingResourcePrefix(resourceRef);
                        if (prefix.Length == 0 ||
                            ValidateResourceRef(
                                resourceRef,
                                prefix,
                                ".vam",
                                false,
                                "clothing items").Length != 0)
                        {
                            resourceRef = "";
                        }
                    }
                    catch
                    {
                        resourceRef = "";
                    }
                }
                ActiveClothingEntry entry = new ActiveClothingEntry();
                entry.Item = item;
                entry.ResourceRef = resourceRef;
                entry.Uid = item.uid ?? "";
                entry.InternalUid = item.internalUid ?? "";
                entry.PackageUid = item.packageUid ?? "";
                entry.DisplayName = SanitizeRosterText(
                    item.displayName,
                    MaximumRosterDisplayNameLength);
                if (entry.DisplayName.Length == 0)
                {
                    entry.DisplayName = "Unnamed clothing item";
                }
                entry.Tags = SanitizeRosterTags(item.tagsArray);
                entry.Locked = item.locked;
                result.Add(entry);
            }
            result.Sort(CompareActiveClothingEntries);
            return result;
        }

        private static bool IsAllowlistedBodyProportionMorphName(
            string name)
        {
            return
                name == "Body Scale" ||
                name == "Lower Body Length" ||
                name == "Legs Length" ||
                name == "Upper Body Length" ||
                name == "Upper Torso Length" ||
                name == "Shoulder Width" ||
                name == "Shoulder Width (B)";
        }

        private static string BodyShapeRegionForMorphName(
            string name)
        {
            if (name == "Breasts Size")
            {
                return "breasts";
            }
            if (name == "ChestSeparateBreasts")
            {
                return "breasts";
            }
            if (name == "Waist Width")
            {
                return "waist";
            }
            if (name == "Hip Size")
            {
                return "hips";
            }
            if (name == "Glutes Size")
            {
                return "glutes";
            }
            if (name == "Thighs Size")
            {
                return "thighs";
            }
            return "";
        }

        private static bool IsAllowlistedBodyShapeMorphName(
            string name)
        {
            return BodyShapeRegionForMorphName(name).Length != 0;
        }

        private static bool IsBodyShapeCalibrationMorphName(
            string name)
        {
            return
                IsAllowlistedBodyShapeMorphName(name) &&
                name != "ChestSeparateBreasts";
        }

        private static bool IsEligibleBodyProportionMorph(
            DAZMorphBank bank,
            DAZMorph morph)
        {
            if (bank == null ||
                morph == null ||
                !morph.visible ||
                morph.disable ||
                morph.isPoseControl ||
                morph.isDriven ||
                !morph.isLatestVersion ||
                morph.isInPackage ||
                morph.isRuntime ||
                morph.isTransient ||
                !IsFinite(morph.morphValue) ||
                Mathf.Abs(morph.morphValue) >
                    MaximumBodyProportionMagnitude)
            {
                return false;
            }
            string name = morph.resolvedDisplayName ?? "";
            bool structural =
                IsAllowlistedBodyProportionMorphName(name);
            bool shape =
                IsAllowlistedBodyShapeMorphName(name);
            if (!structural && !shape)
            {
                return false;
            }
            if (shape &&
                (
                    morph.hasBoneModificationFormulas ||
                    (
                        morph.group != null &&
                        morph.group.IndexOf(
                            "Pose/",
                            StringComparison.OrdinalIgnoreCase) >= 0)))
            {
                return false;
            }
            DAZMorph builtIn =
                bank.GetBuiltInMorphByUid(morph.uid);
            return object.ReferenceEquals(builtIn, morph);
        }

        private static int CompareBodyProportionMorphEntries(
            BodyProportionMorphEntry left,
            BodyProportionMorphEntry right)
        {
            int nameOrder = string.Compare(
                left == null ? "" : left.Name,
                right == null ? "" : right.Name,
                StringComparison.Ordinal);
            if (nameOrder != 0)
            {
                return nameOrder;
            }
            return string.Compare(
                left == null || left.Morph == null
                    ? ""
                    : left.Morph.uid,
                right == null || right.Morph == null
                    ? ""
                    : right.Morph.uid,
                StringComparison.Ordinal);
        }

        private static void AddBodyProportionMorphs(
            List<BodyProportionMorphEntry> result,
            DAZMorphBank bank)
        {
            if (result == null || bank == null || bank.morphs == null)
            {
                return;
            }
            int index;
            for (index = 0;
                 index < bank.morphs.Count &&
                    result.Count < MaximumBodyProportionMorphs;
                 index++)
            {
                DAZMorph morph = bank.morphs[index];
                if (!IsEligibleBodyProportionMorph(bank, morph))
                {
                    continue;
                }
                bool duplicate = false;
                int existingIndex;
                for (existingIndex = 0;
                     existingIndex < result.Count;
                     existingIndex++)
                {
                    if (object.ReferenceEquals(
                            result[existingIndex].Morph,
                            morph))
                    {
                        duplicate = true;
                        break;
                    }
                }
                if (duplicate)
                {
                    continue;
                }
                float minimum = Mathf.Max(
                    morph.min,
                    -MaximumBodyProportionMagnitude);
                float maximum = Mathf.Min(
                    morph.max,
                    MaximumBodyProportionMagnitude);
                if (!IsFinite(minimum) ||
                    !IsFinite(maximum) ||
                    minimum > maximum ||
                    morph.morphValue < minimum ||
                    morph.morphValue > maximum)
                {
                    continue;
                }
                BodyProportionMorphEntry entry =
                    new BodyProportionMorphEntry();
                entry.Morph = morph;
                entry.Bank = bank;
                entry.Name = morph.resolvedDisplayName ?? "";
                entry.Region = morph.resolvedRegionName ?? "";
                entry.ShapeRegion =
                    BodyShapeRegionForMorphName(entry.Name);
                entry.FitKind =
                    entry.ShapeRegion.Length == 0
                    ? "structure"
                    : "shape";
                entry.ShapeResponses = null;
                entry.Value = morph.morphValue;
                entry.Minimum = minimum;
                entry.Maximum = maximum;
                result.Add(entry);
            }
        }

        private static List<BodyProportionMorphEntry>
            GetBodyProportionMorphEntries(
                DAZCharacterSelector geometry)
        {
            List<BodyProportionMorphEntry> result =
                new List<BodyProportionMorphEntry>();
            if (geometry == null)
            {
                return result;
            }
            AddBodyProportionMorphs(result, geometry.morphBank1);
            AddBodyProportionMorphs(result, geometry.morphBank2);
            AddBodyProportionMorphs(result, geometry.morphBank3);
            result.Sort(CompareBodyProportionMorphEntries);
            return result;
        }

        private static string BuildBodyProportionMorphStateKey(
            DAZCharacterSelector geometry,
            List<BodyProportionMorphEntry> entries)
        {
            ulong first = 1469598103934665603UL;
            ulong second = 7809847782465536322UL;
            HashCuaText(
                ref first,
                ref second,
                geometry == null ? "" : geometry.gender.ToString());
            HashBodyProportionBankState(
                ref first,
                ref second,
                geometry == null ? null : geometry.morphBank1);
            HashBodyProportionBankState(
                ref first,
                ref second,
                geometry == null ? null : geometry.morphBank2);
            HashBodyProportionBankState(
                ref first,
                ref second,
                geometry == null ? null : geometry.morphBank3);
            HashCuaText(
                ref first,
                ref second,
                entries == null ? "-1" : entries.Count.ToString());
            if (entries != null)
            {
                int index;
                for (index = 0; index < entries.Count; index++)
                {
                    BodyProportionMorphEntry entry = entries[index];
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.Morph == null ? "" : entry.Morph.uid);
                    HashCuaText(ref first, ref second, entry.Name);
                    HashCuaText(ref first, ref second, entry.Region);
                    HashCuaText(ref first, ref second, entry.FitKind);
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.ShapeRegion);
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.Value.ToString("R"));
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.Minimum.ToString("R"));
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.Maximum.ToString("R"));
                }
            }
            return first.ToString("x16") + second.ToString("x16");
        }

        private static string BuildBodyProportionGenerationKey(
            DAZCharacterSelector geometry,
            List<BodyProportionMorphEntry> entries,
            BodyShapeSignature bodyShape,
            string bodyShapeMeshChecksum)
        {
            ulong first = 1469598103934665603UL;
            ulong second = 7809847782465536322UL;
            HashCuaText(
                ref first,
                ref second,
                BuildBodyProportionMorphStateKey(
                    geometry,
                    entries));
            HashBodyShapeSignature(
                ref first,
                ref second,
                bodyShape);
            HashCuaText(
                ref first,
                ref second,
                bodyShapeMeshChecksum ?? "");
            return first.ToString("x16") + second.ToString("x16");
        }

        private static void HashBodyShapeSignature(
            ref ulong first,
            ref ulong second,
            BodyShapeSignature signature)
        {
            if (signature == null ||
                signature.Measurements == null)
            {
                HashCuaText(
                    ref first,
                    ref second,
                    "body-shape-unavailable");
                return;
            }
            HashCuaText(
                ref first,
                ref second,
                "body-shape-v1");
            HashCuaText(
                ref first,
                ref second,
                signature.StructuralLength.ToString("R"));
            HashCuaText(
                ref first,
                ref second,
                signature.BustTorsoFraction.ToString("R"));
            HashCuaText(
                ref first,
                ref second,
                signature.UnderbustTorsoFraction.ToString("R"));
            HashCuaText(
                ref first,
                ref second,
                signature.WaistTorsoFraction.ToString("R"));
            HashCuaText(
                ref first,
                ref second,
                signature.SeatTorsoFraction.ToString("R"));
            HashCuaText(
                ref first,
                ref second,
                signature.UpperThighLegFraction.ToString("R"));
            int index;
            for (index = 0;
                 index < BodyShapeMetricNames.Length;
                 index++)
            {
                string name = BodyShapeMetricNames[index];
                BodyShapeMetric metric = null;
                HashCuaText(ref first, ref second, name);
                if (!signature.Measurements.TryGetValue(
                        name,
                        out metric) ||
                    metric == null)
                {
                    HashCuaText(ref first, ref second, "missing");
                    continue;
                }
                HashCuaText(
                    ref first,
                    ref second,
                    metric.Meters.ToString("R"));
                if (metric.Bilateral)
                {
                    HashCuaText(
                        ref first,
                        ref second,
                        metric.LeftMeters.ToString("R"));
                    HashCuaText(
                        ref first,
                        ref second,
                        metric.RightMeters.ToString("R"));
                }
            }
        }

        private static void HashBodyProportionBankState(
            ref ulong first,
            ref ulong second,
            DAZMorphBank bank)
        {
            if (bank == null || bank.morphs == null)
            {
                HashCuaText(ref first, ref second, "-1");
                return;
            }
            int structuralCount = 0;
            int index;
            for (index = 0; index < bank.morphs.Count; index++)
            {
                DAZMorph morph = bank.morphs[index];
                if (morph == null ||
                    morph.isPoseControl ||
                    morph.isDriven ||
                    !morph.hasBoneModificationFormulas ||
                    !IsFinite(morph.morphValue))
                {
                    continue;
                }
                structuralCount++;
                HashCuaText(
                    ref first,
                    ref second,
                    morph.uid);
                HashCuaText(
                    ref first,
                    ref second,
                    morph.morphValue.ToString("R"));
                HashCuaText(
                    ref first,
                    ref second,
                    morph.disable ? "disabled" : "enabled");
                HashCuaText(
                    ref first,
                    ref second,
                    morph.isLatestVersion ? "latest" : "superseded");
            }
            HashCuaText(
                ref first,
                ref second,
                structuralCount.ToString());
        }

        private static bool IsCurrentBodyProportionSnapshot(
            PersonBodyProportionSnapshot snapshot,
            List<BodyProportionMorphEntry> current,
            string currentGeneration)
        {
            if (snapshot == null ||
                snapshot.Entries == null ||
                current == null ||
                snapshot.Entries.Count != current.Count ||
                !string.Equals(
                    snapshot.GenerationKey,
                    currentGeneration,
                    StringComparison.Ordinal))
            {
                return false;
            }
            int index;
            for (index = 0; index < current.Count; index++)
            {
                if (!object.ReferenceEquals(
                        snapshot.Entries[index].Morph,
                        current[index].Morph))
                {
                    return false;
                }
            }
            return true;
        }

        private static BodyProportionMorphEntry
            FindBodyProportionEntryByKey(
                List<BodyProportionMorphEntry> entries,
                string key)
        {
            BodyProportionMorphEntry match = null;
            int matches = 0;
            if (entries == null)
            {
                return null;
            }
            int index;
            for (index = 0; index < entries.Count; index++)
            {
                BodyProportionMorphEntry entry = entries[index];
                if (entry != null &&
                    string.Equals(
                        entry.Key,
                        key,
                        StringComparison.OrdinalIgnoreCase))
                {
                    match = entry;
                    matches++;
                }
            }
            return matches == 1 ? match : null;
        }

        private static bool ContainsEligibleBodyProportionMorph(
            List<BodyProportionMorphEntry> entries,
            DAZMorph morph)
        {
            if (entries == null || morph == null)
            {
                return false;
            }
            int index;
            for (index = 0; index < entries.Count; index++)
            {
                if (object.ReferenceEquals(
                        entries[index].Morph,
                        morph))
                {
                    return IsEligibleBodyProportionMorph(
                        entries[index].Bank,
                        morph);
                }
            }
            return false;
        }

        private static DAZBone BodyProportionBone(
            DAZCharacterSelector geometry,
            params string[] names)
        {
            if (geometry == null ||
                geometry.rootBones == null ||
                names == null)
            {
                return null;
            }
            int index;
            for (index = 0; index < names.Length; index++)
            {
                DAZBone bone =
                    geometry.rootBones.GetDAZBone(names[index]);
                if (bone != null)
                {
                    return bone;
                }
            }
            return null;
        }

        private static bool IsFiniteBodyProportionPoint(Vector3 point)
        {
            return
                IsFinite(point.x) &&
                IsFinite(point.y) &&
                IsFinite(point.z) &&
                Mathf.Abs(point.x) <= MaximumSam3dCoordinate &&
                Mathf.Abs(point.y) <= MaximumSam3dCoordinate &&
                Mathf.Abs(point.z) <= MaximumSam3dCoordinate;
        }

        private static bool TryBodyProportionDistance(
            DAZBone first,
            DAZBone second,
            out float distance)
        {
            distance = 0f;
            if (first == null || second == null)
            {
                return false;
            }
            Vector3 firstPoint = first.morphedWorldPosition;
            Vector3 secondPoint = second.morphedWorldPosition;
            if (!IsFiniteBodyProportionPoint(firstPoint) ||
                !IsFiniteBodyProportionPoint(secondPoint))
            {
                return false;
            }
            distance = Vector3.Distance(firstPoint, secondPoint);
            return IsFinite(distance) &&
                distance > 0.000001f &&
                distance <= MaximumSam3dCoordinate;
        }

        private static bool TryBodyProportionMidpointDistance(
            DAZBone firstLeft,
            DAZBone firstRight,
            DAZBone secondLeft,
            DAZBone secondRight,
            out float distance)
        {
            distance = 0f;
            if (firstLeft == null ||
                firstRight == null ||
                secondLeft == null ||
                secondRight == null)
            {
                return false;
            }
            Vector3 firstLeftPoint =
                firstLeft.morphedWorldPosition;
            Vector3 firstRightPoint =
                firstRight.morphedWorldPosition;
            Vector3 secondLeftPoint =
                secondLeft.morphedWorldPosition;
            Vector3 secondRightPoint =
                secondRight.morphedWorldPosition;
            if (!IsFiniteBodyProportionPoint(firstLeftPoint) ||
                !IsFiniteBodyProportionPoint(firstRightPoint) ||
                !IsFiniteBodyProportionPoint(secondLeftPoint) ||
                !IsFiniteBodyProportionPoint(secondRightPoint))
            {
                return false;
            }
            Vector3 firstMidpoint =
                (firstLeftPoint + firstRightPoint) * 0.5f;
            Vector3 secondMidpoint =
                (secondLeftPoint + secondRightPoint) * 0.5f;
            distance =
                Vector3.Distance(firstMidpoint, secondMidpoint);
            return IsFinite(distance) &&
                distance > 0.000001f &&
                distance <= MaximumSam3dCoordinate;
        }

        private static JSONClass UnavailableBodyProportionMeasurement(
            string reason)
        {
            JSONClass result = new JSONClass();
            result["available"].AsBool = false;
            result["reason"] = reason;
            return result;
        }

        private static JSONClass BodyProportionMeasurement(
            float meters,
            float structuralHeight,
            string method)
        {
            JSONClass result = new JSONClass();
            result["available"].AsBool = true;
            result["meters"].AsFloat = meters;
            result["confidence"].AsFloat = 1f;
            result["method"] = method;
            if (structuralHeight > 0.000001f)
            {
                result["ratio"].AsFloat =
                    meters / structuralHeight;
            }
            return result;
        }

        private static JSONClass PairedBodyProportionMeasurement(
            DAZBone leftStart,
            DAZBone leftEnd,
            DAZBone rightStart,
            DAZBone rightEnd,
            float structuralHeight,
            string method)
        {
            float left;
            float right;
            bool hasLeft = TryBodyProportionDistance(
                leftStart,
                leftEnd,
                out left);
            bool hasRight = TryBodyProportionDistance(
                rightStart,
                rightEnd,
                out right);
            if (!hasLeft && !hasRight)
            {
                return UnavailableBodyProportionMeasurement(
                    "Required neutral-bind bones are unavailable.");
            }
            float average =
                hasLeft && hasRight
                ? (left + right) * 0.5f
                : hasLeft
                ? left
                : right;
            JSONClass result =
                BodyProportionMeasurement(
                    average,
                    structuralHeight,
                    method);
            if (hasLeft)
            {
                result["leftMeters"].AsFloat = left;
            }
            if (hasRight)
            {
                result["rightMeters"].AsFloat = right;
            }
            result["bilateral"].AsBool = hasLeft && hasRight;
            if (!hasLeft || !hasRight)
            {
                result["reason"] =
                    "Only one side was available; meters is the available side.";
            }
            return result;
        }

        private static bool TryBuildBodyShapeFrame(
            DAZCharacterSelector geometry,
            DAZSkinV2 skin,
            out BodyShapeFrame frame)
        {
            frame = null;
            DAZBone leftShoulder =
                BodyProportionBone(
                    geometry,
                    "lShldr",
                    "lShoulder");
            DAZBone rightShoulder =
                BodyProportionBone(
                    geometry,
                    "rShldr",
                    "rShoulder");
            DAZBone leftThigh =
                BodyProportionBone(geometry, "lThigh");
            DAZBone rightThigh =
                BodyProportionBone(geometry, "rThigh");
            DAZBone leftShin =
                BodyProportionBone(geometry, "lShin");
            DAZBone rightShin =
                BodyProportionBone(geometry, "rShin");
            DAZBone leftFoot =
                geometry == null ? null : geometry.leftFootBone;
            if (leftFoot == null)
            {
                leftFoot = BodyProportionBone(geometry, "lFoot");
            }
            DAZBone rightFoot =
                geometry == null ? null : geometry.rightFootBone;
            if (rightFoot == null)
            {
                rightFoot = BodyProportionBone(geometry, "rFoot");
            }
            Vector3 leftShoulderPoint;
            Vector3 rightShoulderPoint;
            Vector3 leftThighPoint;
            Vector3 rightThighPoint;
            Vector3 leftShinPoint;
            Vector3 rightShinPoint;
            Vector3 leftFootPoint;
            Vector3 rightFootPoint;
            if (!TryBodyShapeBoneLocalPoint(
                    skin,
                    leftShoulder,
                    out leftShoulderPoint) ||
                !TryBodyShapeBoneLocalPoint(
                    skin,
                    rightShoulder,
                    out rightShoulderPoint) ||
                !TryBodyShapeBoneLocalPoint(
                    skin,
                    leftThigh,
                    out leftThighPoint) ||
                !TryBodyShapeBoneLocalPoint(
                    skin,
                    rightThigh,
                    out rightThighPoint) ||
                !TryBodyShapeBoneLocalPoint(
                    skin,
                    leftShin,
                    out leftShinPoint) ||
                !TryBodyShapeBoneLocalPoint(
                    skin,
                    rightShin,
                    out rightShinPoint) ||
                !TryBodyShapeBoneLocalPoint(
                    skin,
                    leftFoot,
                    out leftFootPoint) ||
                !TryBodyShapeBoneLocalPoint(
                    skin,
                    rightFoot,
                    out rightFootPoint))
            {
                return false;
            }
            Vector3 shoulderCenter =
                (
                    leftShoulderPoint +
                    rightShoulderPoint) * 0.5f;
            Vector3 thighCenter =
                (
                    leftThighPoint +
                    rightThighPoint) * 0.5f;
            Vector3 lateral =
                leftShoulderPoint - rightShoulderPoint;
            float shoulderSpan = lateral.magnitude;
            if (!IsFinite(shoulderSpan) ||
                shoulderSpan <= 0.000001f)
            {
                return false;
            }
            lateral /= shoulderSpan;
            Vector3 up = shoulderCenter - thighCenter;
            up -= lateral * Vector3.Dot(up, lateral);
            float torsoLength = up.magnitude;
            if (!IsFinite(torsoLength) ||
                torsoLength <= 0.000001f)
            {
                return false;
            }
            up /= torsoLength;
            Vector3 front =
                Vector3.Cross(lateral, up);
            float frontMagnitude = front.magnitude;
            if (!IsFinite(frontMagnitude) ||
                frontMagnitude <= 0.000001f)
            {
                return false;
            }
            front /= frontMagnitude;
            Vector3 localForward =
                skin.transform.InverseTransformDirection(
                    skin.transform.forward);
            if (Vector3.Dot(front, localForward) < 0f)
            {
                front = -front;
            }
            float localThighLength =
                (
                    Vector3.Distance(
                        leftThighPoint,
                        leftShinPoint) +
                    Vector3.Distance(
                        rightThighPoint,
                        rightShinPoint)) * 0.5f;
            float localShinLength =
                (
                    Vector3.Distance(
                        leftShinPoint,
                        leftFootPoint) +
                    Vector3.Distance(
                        rightShinPoint,
                        rightFootPoint)) * 0.5f;
            float localStructuralLength =
                torsoLength +
                localThighLength +
                localShinLength;
            float structuralLength =
                skin.transform.TransformVector(
                    up * torsoLength).magnitude +
                (
                    skin.transform.TransformVector(
                        leftShinPoint -
                        leftThighPoint).magnitude +
                    skin.transform.TransformVector(
                        rightShinPoint -
                        rightThighPoint).magnitude) * 0.5f +
                (
                    skin.transform.TransformVector(
                        leftFootPoint -
                        leftShinPoint).magnitude +
                    skin.transform.TransformVector(
                        rightFootPoint -
                        rightShinPoint).magnitude) * 0.5f;
            Vector3 kneeCenter =
                (
                    leftShinPoint +
                    rightShinPoint) * 0.5f;
            float hipToKnee =
                Vector3.Dot(
                    thighCenter - kneeCenter,
                    up);
            if (!IsFinite(structuralLength) ||
                structuralLength < 0.25f ||
                structuralLength > 4.0f ||
                !IsFinite(localStructuralLength) ||
                localStructuralLength <= 0.000001f ||
                !IsFinite(hipToKnee) ||
                hipToKnee < 0.05f ||
                hipToKnee >= localStructuralLength)
            {
                return false;
            }
            BodyShapeFrame measured =
                new BodyShapeFrame();
            measured.Origin = thighCenter;
            measured.Lateral = lateral;
            measured.Up = up;
            measured.Front = front;
            measured.LeftThigh = leftThighPoint;
            measured.RightThigh = rightThighPoint;
            measured.LeftShin = leftShinPoint;
            measured.RightShin = rightShinPoint;
            measured.TorsoLength = torsoLength;
            measured.HipToKnee = hipToKnee;
            measured.StructuralLength = structuralLength;
            measured.ShoulderSpan = shoulderSpan;
            frame = measured;
            return true;
        }

        private static bool TryBodyShapeMesh(
            DAZCharacterSelector geometry,
            out DAZSkinV2 skin,
            out Vector3[] vertices,
            out int[] triangles)
        {
            skin = null;
            vertices = null;
            triangles = null;
            if (geometry == null ||
                geometry.selectedCharacter == null ||
                !geometry.selectedCharacter.ready)
            {
                return false;
            }
            skin = geometry.selectedCharacter.skin;
            if (skin == null ||
                !skin.wasInit ||
                skin.dazMesh == null)
            {
                return false;
            }
            vertices = skin.dazMesh.morphedBaseVertices;
            triangles = skin.dazMesh.baseTriangles;
            return
                vertices != null &&
                vertices.Length >= 1000 &&
                triangles != null &&
                triangles.Length >= 3 &&
                triangles.Length % 3 == 0;
        }

        private static void MixBodyShapeChecksum(
            ref ulong first,
            ref ulong second,
            int value)
        {
            unchecked
            {
                uint encoded = (uint)value;
                first ^= encoded;
                first *= 1099511628211UL;
                second +=
                    encoded +
                    0x9e3779b9UL +
                    (second << 6) +
                    (second >> 2);
            }
        }

        private static void MixBodyShapeVector(
            ref ulong first,
            ref ulong second,
            Vector3 value)
        {
            MixBodyShapeChecksum(
                ref first,
                ref second,
                Mathf.RoundToInt(value.x * 1000000f));
            MixBodyShapeChecksum(
                ref first,
                ref second,
                Mathf.RoundToInt(value.y * 1000000f));
            MixBodyShapeChecksum(
                ref first,
                ref second,
                Mathf.RoundToInt(value.z * 1000000f));
        }

        private static bool TryBodyShapeMeshChecksum(
            DAZCharacterSelector geometry,
            out string checksum)
        {
            checksum = "";
            DAZSkinV2 skin;
            Vector3[] vertices;
            int[] triangles;
            if (!TryBodyShapeMesh(
                    geometry,
                    out skin,
                    out vertices,
                    out triangles))
            {
                return false;
            }
            ulong first = 1469598103934665603UL;
            ulong second = 7809847782465536322UL;
            MixBodyShapeChecksum(
                ref first,
                ref second,
                vertices.Length);
            MixBodyShapeChecksum(
                ref first,
                ref second,
                triangles.Length);
            BodyShapeFrame frame;
            if (!TryBuildBodyShapeFrame(
                    geometry,
                    skin,
                    out frame))
            {
                return false;
            }
            MixBodyShapeVector(
                ref first,
                ref second,
                frame.Origin);
            MixBodyShapeVector(
                ref first,
                ref second,
                frame.Lateral);
            MixBodyShapeVector(
                ref first,
                ref second,
                frame.Up);
            MixBodyShapeVector(
                ref first,
                ref second,
                frame.Front);
            MixBodyShapeChecksum(
                ref first,
                ref second,
                Mathf.RoundToInt(
                    frame.TorsoLength * 1000000f));
            MixBodyShapeChecksum(
                ref first,
                ref second,
                Mathf.RoundToInt(
                    frame.HipToKnee * 1000000f));
            MixBodyShapeChecksum(
                ref first,
                ref second,
                Mathf.RoundToInt(
                    frame.StructuralLength * 1000000f));
            int index;
            for (index = 0; index < vertices.Length; index++)
            {
                Vector3 point = vertices[index];
                if (!IsFiniteBodyProportionPoint(point))
                {
                    return false;
                }
                MixBodyShapeChecksum(
                    ref first,
                    ref second,
                    Mathf.RoundToInt(point.x * 1000000f));
                MixBodyShapeChecksum(
                    ref first,
                    ref second,
                    Mathf.RoundToInt(point.y * 1000000f));
                MixBodyShapeChecksum(
                    ref first,
                    ref second,
                    Mathf.RoundToInt(point.z * 1000000f));
            }
            checksum =
                first.ToString("x16") +
                second.ToString("x16");
            return true;
        }

        private static bool TryBodyShapeBoneLocalPoint(
            DAZSkinV2 skin,
            DAZBone bone,
            out Vector3 point)
        {
            point = Vector3.zero;
            if (skin == null || bone == null)
            {
                return false;
            }
            point =
                skin.transform.InverseTransformPoint(
                    bone.morphedWorldPosition);
            return IsFiniteBodyProportionPoint(point);
        }

        private static bool TryBodyShapeEdgeIntersection(
            Vector3 first,
            Vector3 second,
            BodyShapeFrame frame,
            float planeOffset,
            out Vector2 point)
        {
            point = Vector2.zero;
            const float epsilon = 0.0000001f;
            if (frame == null)
            {
                return false;
            }
            float firstDistance =
                Vector3.Dot(
                    first - frame.Origin,
                    frame.Up) -
                planeOffset;
            float secondDistance =
                Vector3.Dot(
                    second - frame.Origin,
                    frame.Up) -
                planeOffset;
            if (
                (
                    firstDistance > epsilon &&
                    secondDistance > epsilon) ||
                (
                    firstDistance < -epsilon &&
                    secondDistance < -epsilon) ||
                (
                    Mathf.Abs(firstDistance) <= epsilon &&
                    Mathf.Abs(secondDistance) <= epsilon))
            {
                return false;
            }
            float denominator =
                firstDistance - secondDistance;
            if (Mathf.Abs(denominator) <= epsilon)
            {
                return false;
            }
            float amount =
                Mathf.Clamp01(firstDistance / denominator);
            Vector3 intersection =
                Vector3.Lerp(first, second, amount) -
                frame.Origin;
            point = new Vector2(
                Vector3.Dot(
                    intersection,
                    frame.Lateral),
                Vector3.Dot(
                    intersection,
                    frame.Front));
            return IsFinite(point.x) && IsFinite(point.y);
        }

        private static int AddUniqueBodyShapeIntersection(
            Vector2[] points,
            int count,
            Vector2 point)
        {
            float toleranceSquared =
                BodyShapeLoopJoinTolerance *
                BodyShapeLoopJoinTolerance;
            int index;
            for (index = 0; index < count; index++)
            {
                if ((points[index] - point).sqrMagnitude <=
                    toleranceSquared)
                {
                    return count;
                }
            }
            if (count < points.Length)
            {
                points[count] = point;
                return count + 1;
            }
            return count;
        }

        private static List<BodyShapeSegment>
            BuildBodyShapeSegments(
                Vector3[] vertices,
                int[] triangles,
                BodyShapeFrame frame,
                float planeOffset)
        {
            List<BodyShapeSegment> segments =
                new List<BodyShapeSegment>();
            if (vertices == null || triangles == null)
            {
                return segments;
            }
            Vector2[] intersections = new Vector2[3];
            float adjustedOffset =
                planeOffset +
                (
                    frame == null
                    ? 0f
                    : frame.StructuralLength *
                        0.0000001f *
                        0.61803398875f);
            float minimumLengthSquared =
                BodyShapeLoopJoinTolerance *
                BodyShapeLoopJoinTolerance * 0.01f;
            int index;
            for (index = 0;
                 index + 2 < triangles.Length;
                 index += 3)
            {
                int firstIndex = triangles[index];
                int secondIndex = triangles[index + 1];
                int thirdIndex = triangles[index + 2];
                if (firstIndex < 0 ||
                    secondIndex < 0 ||
                    thirdIndex < 0 ||
                    firstIndex >= vertices.Length ||
                    secondIndex >= vertices.Length ||
                    thirdIndex >= vertices.Length)
                {
                    continue;
                }
                Vector3 first = vertices[firstIndex];
                Vector3 second = vertices[secondIndex];
                Vector3 third = vertices[thirdIndex];
                if (!IsFiniteBodyProportionPoint(first) ||
                    !IsFiniteBodyProportionPoint(second) ||
                    !IsFiniteBodyProportionPoint(third))
                {
                    continue;
                }
                int count = 0;
                Vector2 intersection;
                if (TryBodyShapeEdgeIntersection(
                        first,
                        second,
                        frame,
                        adjustedOffset,
                        out intersection))
                {
                    count = AddUniqueBodyShapeIntersection(
                        intersections,
                        count,
                        intersection);
                }
                if (TryBodyShapeEdgeIntersection(
                        second,
                        third,
                        frame,
                        adjustedOffset,
                        out intersection))
                {
                    count = AddUniqueBodyShapeIntersection(
                        intersections,
                        count,
                        intersection);
                }
                if (TryBodyShapeEdgeIntersection(
                        third,
                        first,
                        frame,
                        adjustedOffset,
                        out intersection))
                {
                    count = AddUniqueBodyShapeIntersection(
                        intersections,
                        count,
                        intersection);
                }
                if (count < 2)
                {
                    continue;
                }
                int firstPoint = 0;
                int secondPoint = 1;
                if (count == 3)
                {
                    float firstSecond =
                        (
                            intersections[0] -
                            intersections[1]).sqrMagnitude;
                    float firstThird =
                        (
                            intersections[0] -
                            intersections[2]).sqrMagnitude;
                    float secondThird =
                        (
                            intersections[1] -
                            intersections[2]).sqrMagnitude;
                    if (firstThird >= firstSecond &&
                        firstThird >= secondThird)
                    {
                        secondPoint = 2;
                    }
                    else if (secondThird >= firstSecond)
                    {
                        firstPoint = 1;
                        secondPoint = 2;
                    }
                }
                if (
                    (
                        intersections[firstPoint] -
                        intersections[secondPoint]).sqrMagnitude <=
                    minimumLengthSquared)
                {
                    continue;
                }
                BodyShapeSegment segment =
                    new BodyShapeSegment();
                segment.First = intersections[firstPoint];
                segment.Second = intersections[secondPoint];
                segments.Add(segment);
            }
            return segments;
        }

        private static BodyShapeLoop CreateBodyShapeLoop(
            List<Vector2> points,
            float scaleX,
            float scaleZ)
        {
            if (points == null || points.Count < 3)
            {
                return null;
            }
            BodyShapeLoop loop = new BodyShapeLoop();
            loop.Points = points;
            loop.MinimumX = float.MaxValue;
            loop.MaximumX = float.MinValue;
            loop.MinimumZ = float.MaxValue;
            loop.MaximumZ = float.MinValue;
            float signedArea = 0f;
            float perimeter = 0f;
            Vector2 centroid = Vector2.zero;
            int index;
            for (index = 0; index < points.Count; index++)
            {
                Vector2 current = points[index];
                Vector2 next =
                    points[(index + 1) % points.Count];
                loop.MinimumX =
                    Mathf.Min(loop.MinimumX, current.x);
                loop.MaximumX =
                    Mathf.Max(loop.MaximumX, current.x);
                loop.MinimumZ =
                    Mathf.Min(loop.MinimumZ, current.y);
                loop.MaximumZ =
                    Mathf.Max(loop.MaximumZ, current.y);
                float dx = (next.x - current.x) * scaleX;
                float dz = (next.y - current.y) * scaleZ;
                perimeter += Mathf.Sqrt(dx * dx + dz * dz);
                signedArea +=
                    current.x * next.y -
                    next.x * current.y;
                centroid += current;
            }
            loop.Perimeter = perimeter;
            loop.Area =
                Mathf.Abs(signedArea) *
                0.5f * scaleX * scaleZ;
            loop.Centroid = centroid / points.Count;
            if (!IsFinite(loop.Perimeter) ||
                !IsFinite(loop.Area) ||
                loop.Perimeter <= 0.001f ||
                loop.Area <= 0.000001f)
            {
                return null;
            }
            return loop;
        }

        private static List<BodyShapeLoop> BuildBodyShapeLoops(
            Vector3[] vertices,
            int[] triangles,
            BodyShapeFrame frame,
            float planeOffset,
            float scaleX,
            float scaleZ)
        {
            List<BodyShapeSegment> segments =
                BuildBodyShapeSegments(
                    vertices,
                    triangles,
                    frame,
                    planeOffset);
            List<BodyShapeLoop> loops =
                new List<BodyShapeLoop>();
            float toleranceSquared =
                BodyShapeLoopJoinTolerance *
                BodyShapeLoopJoinTolerance;
            int segmentIndex;
            for (segmentIndex = 0;
                 segmentIndex < segments.Count;
                 segmentIndex++)
            {
                BodyShapeSegment starting =
                    segments[segmentIndex];
                if (starting.Used)
                {
                    continue;
                }
                starting.Used = true;
                List<Vector2> points = new List<Vector2>();
                points.Add(starting.First);
                points.Add(starting.Second);
                bool closed = false;
                int guard = 0;
                while (guard <= segments.Count)
                {
                    guard++;
                    Vector2 end = points[points.Count - 1];
                    if (points.Count >= 4 &&
                        (
                            end -
                            points[0]).sqrMagnitude <=
                        toleranceSquared)
                    {
                        points.RemoveAt(points.Count - 1);
                        closed = true;
                        break;
                    }
                    int bestIndex = -1;
                    bool bestUsesFirst = true;
                    float bestDistance = float.MaxValue;
                    int candidateIndex;
                    for (candidateIndex = 0;
                         candidateIndex < segments.Count;
                         candidateIndex++)
                    {
                        BodyShapeSegment candidate =
                            segments[candidateIndex];
                        if (candidate.Used)
                        {
                            continue;
                        }
                        float firstDistance =
                            (
                                end -
                                candidate.First).sqrMagnitude;
                        if (firstDistance < bestDistance)
                        {
                            bestDistance = firstDistance;
                            bestIndex = candidateIndex;
                            bestUsesFirst = true;
                        }
                        float secondDistance =
                            (
                                end -
                                candidate.Second).sqrMagnitude;
                        if (secondDistance < bestDistance)
                        {
                            bestDistance = secondDistance;
                            bestIndex = candidateIndex;
                            bestUsesFirst = false;
                        }
                    }
                    if (bestIndex < 0 ||
                        bestDistance > toleranceSquared)
                    {
                        break;
                    }
                    BodyShapeSegment best = segments[bestIndex];
                    best.Used = true;
                    points.Add(
                        bestUsesFirst
                        ? best.Second
                        : best.First);
                }
                if (!closed)
                {
                    continue;
                }
                BodyShapeLoop loop =
                    CreateBodyShapeLoop(
                        points,
                        scaleX,
                        scaleZ);
                if (loop != null)
                {
                    loops.Add(loop);
                }
            }
            return loops;
        }

        private static bool BodyShapeLoopContains(
            BodyShapeLoop loop,
            Vector2 target)
        {
            if (loop == null ||
                loop.Points == null ||
                loop.Points.Count < 3 ||
                target.x < loop.MinimumX ||
                target.x > loop.MaximumX ||
                target.y < loop.MinimumZ ||
                target.y > loop.MaximumZ)
            {
                return false;
            }
            bool inside = false;
            int previous = loop.Points.Count - 1;
            int index;
            for (index = 0;
                 index < loop.Points.Count;
                 index++)
            {
                Vector2 currentPoint = loop.Points[index];
                Vector2 previousPoint = loop.Points[previous];
                bool crosses =
                    (
                        currentPoint.y > target.y) !=
                    (
                        previousPoint.y > target.y);
                if (crosses)
                {
                    float crossingX =
                        (
                            previousPoint.x -
                            currentPoint.x) *
                        (
                            target.y -
                            currentPoint.y) /
                        (
                            previousPoint.y -
                            currentPoint.y) +
                        currentPoint.x;
                    if (target.x < crossingX)
                    {
                        inside = !inside;
                    }
                }
                previous = index;
            }
            return inside;
        }

        private static BodyShapeLoop SelectBodyShapeLoop(
            List<BodyShapeLoop> loops,
            Vector2 target,
            BodyShapeLoop excluded)
        {
            BodyShapeLoop bestContaining = null;
            BodyShapeLoop bestNearby = null;
            float bestNearbyDistance = float.MaxValue;
            int index;
            for (index = 0; index < loops.Count; index++)
            {
                BodyShapeLoop loop = loops[index];
                if (loop == null ||
                    object.ReferenceEquals(loop, excluded))
                {
                    continue;
                }
                if (BodyShapeLoopContains(loop, target))
                {
                    if (bestContaining == null ||
                        loop.Area > bestContaining.Area)
                    {
                        bestContaining = loop;
                    }
                    continue;
                }
                float distance =
                    (
                        loop.Centroid -
                        target).sqrMagnitude;
                if (distance < bestNearbyDistance)
                {
                    bestNearbyDistance = distance;
                    bestNearby = loop;
                }
            }
            return bestContaining ?? bestNearby;
        }

        private static bool TryBodyShapeSectionFromLoops(
            List<BodyShapeLoop> loops,
            Vector2 target,
            BodyShapeLoop excluded,
            float scaleX,
            float scaleZ,
            out BodyShapeSection section,
            out BodyShapeLoop selectedLoop)
        {
            section = null;
            selectedLoop =
                SelectBodyShapeLoop(loops, target, excluded);
            if (selectedLoop == null)
            {
                return false;
            }
            BodyShapeSection measured =
                new BodyShapeSection();
            measured.Girth = selectedLoop.Perimeter;
            measured.Width =
                (
                    selectedLoop.MaximumX -
                    selectedLoop.MinimumX) * scaleX;
            measured.Depth =
                (
                    selectedLoop.MaximumZ -
                    selectedLoop.MinimumZ) * scaleZ;
            measured.MinimumX =
                selectedLoop.MinimumX * scaleX;
            measured.MaximumX =
                selectedLoop.MaximumX * scaleX;
            measured.MinimumZ =
                selectedLoop.MinimumZ * scaleZ;
            measured.MaximumZ =
                selectedLoop.MaximumZ * scaleZ;
            if (!IsFinite(measured.Girth) ||
                !IsFinite(measured.Width) ||
                !IsFinite(measured.Depth) ||
                measured.Girth <= 0.001f ||
                measured.Width <= 0.001f ||
                measured.Depth <= 0.001f)
            {
                selectedLoop = null;
                return false;
            }
            section = measured;
            return true;
        }

        private static bool TryBodyShapeSection(
            Vector3[] vertices,
            int[] triangles,
            BodyShapeFrame frame,
            float planeOffset,
            Vector2 target,
            float scaleX,
            float scaleZ,
            out BodyShapeSection section)
        {
            List<BodyShapeLoop> loops =
                BuildBodyShapeLoops(
                    vertices,
                    triangles,
                    frame,
                    planeOffset,
                    scaleX,
                    scaleZ);
            BodyShapeLoop best = null;
            float maximumWidth =
                Mathf.Max(
                    frame.ShoulderSpan * scaleX * 1.65f,
                    frame.StructuralLength * 0.28f);
            int loopIndex;
            for (loopIndex = 0;
                 loopIndex < loops.Count;
                 loopIndex++)
            {
                BodyShapeLoop loop = loops[loopIndex];
                float width =
                    (
                        loop.MaximumX -
                        loop.MinimumX) * scaleX;
                float depth =
                    (
                        loop.MaximumZ -
                        loop.MinimumZ) * scaleZ;
                if (loop.MinimumX > 0f ||
                    loop.MaximumX < 0f ||
                    width <=
                        frame.StructuralLength * 0.04f ||
                    width >= maximumWidth ||
                    depth <=
                        frame.StructuralLength * 0.03f ||
                    depth >=
                        frame.StructuralLength * 0.40f ||
                    loop.Perimeter <=
                        frame.StructuralLength * 0.10f ||
                    loop.Perimeter >=
                        frame.StructuralLength * 2.0f)
                {
                    continue;
                }
                if (best == null ||
                    Mathf.Abs(loop.Centroid.x) <
                        Mathf.Abs(best.Centroid.x))
                {
                    best = loop;
                }
            }
            if (best == null)
            {
                section = null;
                return false;
            }
            List<BodyShapeLoop> selectedLoops =
                new List<BodyShapeLoop>();
            selectedLoops.Add(best);
            BodyShapeLoop selected;
            return TryBodyShapeSectionFromLoops(
                selectedLoops,
                target,
                null,
                scaleX,
                scaleZ,
                out section,
                out selected);
        }

        private static BodyShapeLoop SelectBodyShapeThighLoop(
            List<BodyShapeLoop> loops,
            bool left,
            BodyShapeFrame frame,
            float scaleX,
            float scaleZ)
        {
            BodyShapeLoop best = null;
            int index;
            for (index = 0; index < loops.Count; index++)
            {
                BodyShapeLoop loop = loops[index];
                float width =
                    (
                        loop.MaximumX -
                        loop.MinimumX) * scaleX;
                float depth =
                    (
                        loop.MaximumZ -
                        loop.MinimumZ) * scaleZ;
                if (
                    (
                        left &&
                        loop.Centroid.x <= 0f) ||
                    (
                        !left &&
                        loop.Centroid.x >= 0f) ||
                    width <=
                        frame.StructuralLength * 0.025f ||
                    width >=
                        frame.StructuralLength * 0.25f ||
                    depth <=
                        frame.StructuralLength * 0.025f ||
                    depth >=
                        frame.StructuralLength * 0.25f ||
                    loop.Perimeter <=
                        frame.StructuralLength * 0.10f ||
                    loop.Perimeter >=
                        frame.StructuralLength)
                {
                    continue;
                }
                if (best == null ||
                    loop.Perimeter > best.Perimeter)
                {
                    best = loop;
                }
            }
            return best;
        }

        private static bool TryScanBodyShapeTorsoSection(
            Vector3[] vertices,
            int[] triangles,
            BodyShapeFrame frame,
            float firstFraction,
            float lastFraction,
            int selectionKind,
            float scaleX,
            float scaleZ,
            out float selectedFraction,
            out BodyShapeSection selectedSection)
        {
            selectedFraction = 0f;
            selectedSection = null;
            float bestValue = 0f;
            int count =
                Mathf.RoundToInt(
                    (
                        lastFraction -
                        firstFraction) / 0.01f);
            int index;
            for (index = 0; index <= count; index++)
            {
                float fraction =
                    firstFraction + index * 0.01f;
                BodyShapeSection candidate;
                if (!TryBodyShapeSection(
                        vertices,
                        triangles,
                        frame,
                        fraction * frame.TorsoLength,
                        Vector2.zero,
                        scaleX,
                        scaleZ,
                        out candidate))
                {
                    continue;
                }
                float value =
                    selectionKind == 0
                    ? candidate.MaximumZ
                    : selectionKind == 1
                    ? candidate.Girth
                    : candidate.MinimumZ;
                bool better =
                    selectedSection == null ||
                    (
                        selectionKind == 0 &&
                        value > bestValue) ||
                    (
                        selectionKind != 0 &&
                        value < bestValue);
                if (better)
                {
                    bestValue = value;
                    selectedFraction = fraction;
                    selectedSection = candidate;
                }
            }
            return selectedSection != null;
        }

        private static void AddBodyShapeMetric(
            BodyShapeSignature signature,
            string name,
            string region,
            float meters)
        {
            BodyShapeMetric metric = new BodyShapeMetric();
            metric.Region = region;
            metric.Meters = meters;
            signature.Measurements[name] = metric;
        }

        private static void AddBilateralBodyShapeMetric(
            BodyShapeSignature signature,
            string name,
            string region,
            float leftMeters,
            float rightMeters)
        {
            BodyShapeMetric metric = new BodyShapeMetric();
            metric.Region = region;
            metric.Bilateral = true;
            metric.LeftMeters = leftMeters;
            metric.RightMeters = rightMeters;
            metric.Meters =
                (leftMeters + rightMeters) * 0.5f;
            signature.Measurements[name] = metric;
        }

        private static bool IsValidBodyShapeSignature(
            BodyShapeSignature signature)
        {
            if (signature == null ||
                signature.Measurements == null ||
                signature.Measurements.Count !=
                    BodyShapeMetricNames.Length ||
                !IsFinite(signature.StructuralLength) ||
                signature.StructuralLength < 0.25f ||
                signature.StructuralLength > 4.0f ||
                signature.BustTorsoFraction <
                    BodyShapeBustFirstFraction ||
                signature.BustTorsoFraction >
                    BodyShapeBustLastFraction ||
                signature.UnderbustTorsoFraction < 0.50f ||
                signature.UnderbustTorsoFraction > 0.64f ||
                signature.WaistTorsoFraction <
                    BodyShapeWaistFirstFraction ||
                signature.WaistTorsoFraction >
                    BodyShapeWaistLastFraction ||
                signature.SeatTorsoFraction <
                    BodyShapeSeatFirstFraction ||
                signature.SeatTorsoFraction >
                    BodyShapeSeatLastFraction ||
                signature.UpperThighLegFraction < 0.30f ||
                signature.UpperThighLegFraction > 0.40f)
            {
                return false;
            }
            int index;
            for (index = 0;
                 index < BodyShapeMetricNames.Length;
                 index++)
            {
                string name = BodyShapeMetricNames[index];
                BodyShapeMetric metric = null;
                if (!signature.Measurements.TryGetValue(
                        name,
                        out metric) ||
                    metric == null ||
                    !IsFinite(metric.Meters))
                {
                    return false;
                }
                bool signed =
                    name == "breastGirthExcess" ||
                    name == "breastDepthExcess" ||
                    name == "breastProjection" ||
                    name == "gluteProjection";
                if (
                    (
                        signed &&
                        Mathf.Abs(metric.Meters) >=
                            signature.StructuralLength) ||
                    (
                        !signed &&
                        (
                            metric.Meters <= 0.000001f ||
                            metric.Meters >=
                                signature.StructuralLength * 4.0f)))
                {
                    return false;
                }
                if (metric.Bilateral &&
                    (
                        !IsFinite(metric.LeftMeters) ||
                        !IsFinite(metric.RightMeters) ||
                        metric.LeftMeters <= 0.000001f ||
                        metric.RightMeters <= 0.000001f))
                {
                    return false;
                }
            }
            return true;
        }

        private static bool TryBuildBodyShapeSignature(
            DAZCharacterSelector geometry,
            Vector3[] verticesOverride,
            out BodyShapeSignature signature)
        {
            signature = null;
            DAZSkinV2 skin;
            Vector3[] currentVertices;
            int[] triangles;
            if (!TryBodyShapeMesh(
                    geometry,
                    out skin,
                    out currentVertices,
                    out triangles))
            {
                return false;
            }
            Vector3[] vertices =
                verticesOverride ?? currentVertices;
            if (vertices == null ||
                vertices.Length != currentVertices.Length)
            {
                return false;
            }
            BodyShapeFrame frame;
            if (!TryBuildBodyShapeFrame(
                    geometry,
                    skin,
                    out frame))
            {
                return false;
            }

            float scaleX =
                skin.transform.TransformVector(
                    frame.Lateral).magnitude;
            float scaleZ =
                skin.transform.TransformVector(
                    frame.Front).magnitude;
            if (!IsFinite(scaleX) ||
                !IsFinite(scaleZ) ||
                scaleX <= 0.000001f ||
                scaleZ <= 0.000001f)
            {
                return false;
            }

            BodyShapeSection bust;
            BodyShapeSection underbust;
            BodyShapeSection waist;
            BodyShapeSection seat;
            float bustFraction;
            float waistFraction;
            float seatFraction;
            if (!TryScanBodyShapeTorsoSection(
                    vertices,
                    triangles,
                    frame,
                    BodyShapeBustFirstFraction,
                    BodyShapeBustLastFraction,
                    0,
                    scaleX,
                    scaleZ,
                    out bustFraction,
                    out bust) ||
                !TryScanBodyShapeTorsoSection(
                    vertices,
                    triangles,
                    frame,
                    BodyShapeWaistFirstFraction,
                    BodyShapeWaistLastFraction,
                    1,
                    scaleX,
                    scaleZ,
                    out waistFraction,
                    out waist) ||
                !TryScanBodyShapeTorsoSection(
                    vertices,
                    triangles,
                    frame,
                    BodyShapeSeatFirstFraction,
                    BodyShapeSeatLastFraction,
                    2,
                    scaleX,
                    scaleZ,
                    out seatFraction,
                    out seat))
            {
                return false;
            }
            float underbustFraction =
                Mathf.Max(
                    0.50f,
                    Mathf.Min(
                        0.64f,
                        bustFraction - 0.14f));
            if (
                !TryBodyShapeSection(
                    vertices,
                    triangles,
                    frame,
                    underbustFraction *
                        frame.TorsoLength,
                    Vector2.zero,
                    scaleX,
                    scaleZ,
                    out underbust))
            {
                return false;
            }

            List<BodyShapeLoop> thighLoops =
                BuildBodyShapeLoops(
                    vertices,
                    triangles,
                    frame,
                    -BodyShapeUpperThighLegFraction *
                        frame.HipToKnee,
                    scaleX,
                    scaleZ);
            BodyShapeSection leftThighSection;
            BodyShapeSection rightThighSection;
            BodyShapeLoop leftThighLoop =
                SelectBodyShapeThighLoop(
                    thighLoops,
                    true,
                    frame,
                    scaleX,
                    scaleZ);
            BodyShapeLoop rightThighLoop =
                SelectBodyShapeThighLoop(
                    thighLoops,
                    false,
                    frame,
                    scaleX,
                    scaleZ);
            List<BodyShapeLoop> leftThighLoops =
                new List<BodyShapeLoop>();
            List<BodyShapeLoop> rightThighLoops =
                new List<BodyShapeLoop>();
            if (leftThighLoop != null)
            {
                leftThighLoops.Add(leftThighLoop);
            }
            if (rightThighLoop != null)
            {
                rightThighLoops.Add(rightThighLoop);
            }
            if (!TryBodyShapeSectionFromLoops(
                    leftThighLoops,
                    Vector2.zero,
                    null,
                    scaleX,
                    scaleZ,
                    out leftThighSection,
                    out leftThighLoop) ||
                !TryBodyShapeSectionFromLoops(
                    rightThighLoops,
                    Vector2.zero,
                    null,
                    scaleX,
                    scaleZ,
                    out rightThighSection,
                    out rightThighLoop))
            {
                return false;
            }
            float meanThighGirth =
                (
                    leftThighSection.Girth +
                    rightThighSection.Girth) * 0.5f;
            if (Mathf.Abs(
                    leftThighSection.Girth -
                    rightThighSection.Girth) /
                    Mathf.Max(meanThighGirth, 0.00000001f) >
                0.35f)
            {
                return false;
            }

            BodyShapeSignature measured =
                new BodyShapeSignature();
            measured.StructuralLength =
                frame.StructuralLength;
            measured.BustTorsoFraction = bustFraction;
            measured.UnderbustTorsoFraction =
                underbustFraction;
            measured.WaistTorsoFraction =
                waistFraction;
            measured.SeatTorsoFraction = seatFraction;
            measured.UpperThighLegFraction =
                BodyShapeUpperThighLegFraction;
            measured.Measurements =
                new Dictionary<string, BodyShapeMetric>();
            AddBodyShapeMetric(
                measured,
                "bustGirth",
                "breasts",
                bust.Girth);
            AddBodyShapeMetric(
                measured,
                "bustWidth",
                "breasts",
                bust.Width);
            AddBodyShapeMetric(
                measured,
                "bustDepth",
                "breasts",
                bust.Depth);
            AddBodyShapeMetric(
                measured,
                "underbustGirth",
                "breasts",
                underbust.Girth);
            AddBodyShapeMetric(
                measured,
                "underbustWidth",
                "breasts",
                underbust.Width);
            AddBodyShapeMetric(
                measured,
                "underbustDepth",
                "breasts",
                underbust.Depth);
            AddBodyShapeMetric(
                measured,
                "breastGirthExcess",
                "breasts",
                bust.Girth - underbust.Girth);
            AddBodyShapeMetric(
                measured,
                "breastDepthExcess",
                "breasts",
                bust.Depth - underbust.Depth);
            AddBodyShapeMetric(
                measured,
                "breastProjection",
                "breasts",
                bust.MaximumZ - underbust.MaximumZ);
            AddBodyShapeMetric(
                measured,
                "waistGirth",
                "waist",
                waist.Girth);
            AddBodyShapeMetric(
                measured,
                "waistWidth",
                "waist",
                waist.Width);
            AddBodyShapeMetric(
                measured,
                "waistDepth",
                "waist",
                waist.Depth);
            AddBodyShapeMetric(
                measured,
                "seatGirth",
                "hips",
                seat.Girth);
            AddBodyShapeMetric(
                measured,
                "seatWidth",
                "hips",
                seat.Width);
            AddBodyShapeMetric(
                measured,
                "seatDepth",
                "glutes",
                seat.Depth);
            AddBodyShapeMetric(
                measured,
                "gluteProjection",
                "glutes",
                waist.MinimumZ - seat.MinimumZ);
            AddBilateralBodyShapeMetric(
                measured,
                "upperThighGirth",
                "thighs",
                leftThighSection.Girth,
                rightThighSection.Girth);
            AddBilateralBodyShapeMetric(
                measured,
                "upperThighWidth",
                "thighs",
                leftThighSection.Width,
                rightThighSection.Width);
            AddBilateralBodyShapeMetric(
                measured,
                "upperThighDepth",
                "thighs",
                leftThighSection.Depth,
                rightThighSection.Depth);
            if (!IsValidBodyShapeSignature(measured))
            {
                return false;
            }
            signature = measured;
            return true;
        }

        private static BodyShapeSignature BuildBodyShapeWorkResult(
            BodyShapeSignatureWork work)
        {
            if (work == null ||
                work.Frame == null ||
                work.Bust == null ||
                work.Underbust == null ||
                work.Waist == null ||
                work.Seat == null ||
                work.LeftThigh == null ||
                work.RightThigh == null)
            {
                return null;
            }
            BodyShapeSignature measured =
                new BodyShapeSignature();
            measured.StructuralLength =
                work.Frame.StructuralLength;
            measured.BustTorsoFraction =
                work.BustFraction;
            measured.UnderbustTorsoFraction =
                work.UnderbustFraction;
            measured.WaistTorsoFraction =
                work.WaistFraction;
            measured.SeatTorsoFraction =
                work.SeatFraction;
            measured.UpperThighLegFraction =
                BodyShapeUpperThighLegFraction;
            measured.Measurements =
                new Dictionary<string, BodyShapeMetric>();
            AddBodyShapeMetric(
                measured,
                "bustGirth",
                "breasts",
                work.Bust.Girth);
            AddBodyShapeMetric(
                measured,
                "bustWidth",
                "breasts",
                work.Bust.Width);
            AddBodyShapeMetric(
                measured,
                "bustDepth",
                "breasts",
                work.Bust.Depth);
            AddBodyShapeMetric(
                measured,
                "underbustGirth",
                "breasts",
                work.Underbust.Girth);
            AddBodyShapeMetric(
                measured,
                "underbustWidth",
                "breasts",
                work.Underbust.Width);
            AddBodyShapeMetric(
                measured,
                "underbustDepth",
                "breasts",
                work.Underbust.Depth);
            AddBodyShapeMetric(
                measured,
                "breastGirthExcess",
                "breasts",
                work.Bust.Girth -
                    work.Underbust.Girth);
            AddBodyShapeMetric(
                measured,
                "breastDepthExcess",
                "breasts",
                work.Bust.Depth -
                    work.Underbust.Depth);
            AddBodyShapeMetric(
                measured,
                "breastProjection",
                "breasts",
                work.Bust.MaximumZ -
                    work.Underbust.MaximumZ);
            AddBodyShapeMetric(
                measured,
                "waistGirth",
                "waist",
                work.Waist.Girth);
            AddBodyShapeMetric(
                measured,
                "waistWidth",
                "waist",
                work.Waist.Width);
            AddBodyShapeMetric(
                measured,
                "waistDepth",
                "waist",
                work.Waist.Depth);
            AddBodyShapeMetric(
                measured,
                "seatGirth",
                "hips",
                work.Seat.Girth);
            AddBodyShapeMetric(
                measured,
                "seatWidth",
                "hips",
                work.Seat.Width);
            AddBodyShapeMetric(
                measured,
                "seatDepth",
                "glutes",
                work.Seat.Depth);
            AddBodyShapeMetric(
                measured,
                "gluteProjection",
                "glutes",
                work.Waist.MinimumZ -
                    work.Seat.MinimumZ);
            AddBilateralBodyShapeMetric(
                measured,
                "upperThighGirth",
                "thighs",
                work.LeftThigh.Girth,
                work.RightThigh.Girth);
            AddBilateralBodyShapeMetric(
                measured,
                "upperThighWidth",
                "thighs",
                work.LeftThigh.Width,
                work.RightThigh.Width);
            AddBilateralBodyShapeMetric(
                measured,
                "upperThighDepth",
                "thighs",
                work.LeftThigh.Depth,
                work.RightThigh.Depth);
            return
                IsValidBodyShapeSignature(measured)
                ? measured
                : null;
        }

        private static BodyShapeSignatureWork
            CreateBodyShapeSignatureWork(
                Vector3[] vertices,
                int[] triangles,
                BodyShapeFrame frame,
                float scaleX,
                float scaleZ)
        {
            if (vertices == null ||
                triangles == null ||
                frame == null ||
                !IsFinite(scaleX) ||
                !IsFinite(scaleZ) ||
                scaleX <= 0.000001f ||
                scaleZ <= 0.000001f)
            {
                return null;
            }
            BodyShapeSignatureWork work =
                new BodyShapeSignatureWork();
            work.Vertices = vertices;
            work.Triangles = triangles;
            work.Frame = frame;
            work.ScaleX = scaleX;
            work.ScaleZ = scaleZ;
            return work;
        }

        private static void FailBodyShapeSignatureWork(
            BodyShapeSignatureWork work)
        {
            work.Failed = true;
            work.Complete = true;
            work.Result = null;
        }

        private static void StepBodyShapeSignatureWork(
            BodyShapeSignatureWork work)
        {
            if (work == null ||
                work.Complete ||
                work.Failed)
            {
                return;
            }
            if (work.Phase == 0)
            {
                int count =
                    Mathf.RoundToInt(
                        (
                            BodyShapeBustLastFraction -
                            BodyShapeBustFirstFraction) /
                        0.01f);
                if (work.ScanIndex <= count)
                {
                    float fraction =
                        BodyShapeBustFirstFraction +
                        work.ScanIndex * 0.01f;
                    BodyShapeSection candidate;
                    if (TryBodyShapeSection(
                            work.Vertices,
                            work.Triangles,
                            work.Frame,
                            fraction *
                                work.Frame.TorsoLength,
                            Vector2.zero,
                            work.ScaleX,
                            work.ScaleZ,
                            out candidate) &&
                        (
                            work.Bust == null ||
                            candidate.MaximumZ >
                                work.Bust.MaximumZ))
                    {
                        work.Bust = candidate;
                        work.BustFraction = fraction;
                    }
                    work.ScanIndex++;
                    return;
                }
                if (work.Bust == null)
                {
                    FailBodyShapeSignatureWork(work);
                    return;
                }
                work.UnderbustFraction =
                    Mathf.Max(
                        0.50f,
                        Mathf.Min(
                            0.64f,
                            work.BustFraction - 0.14f));
                work.Phase = 1;
                work.ScanIndex = 0;
                return;
            }
            if (work.Phase == 1)
            {
                if (!TryBodyShapeSection(
                        work.Vertices,
                        work.Triangles,
                        work.Frame,
                        work.UnderbustFraction *
                            work.Frame.TorsoLength,
                        Vector2.zero,
                        work.ScaleX,
                        work.ScaleZ,
                        out work.Underbust))
                {
                    FailBodyShapeSignatureWork(work);
                    return;
                }
                work.Phase = 2;
                work.ScanIndex = 0;
                return;
            }
            if (work.Phase == 2)
            {
                int count =
                    Mathf.RoundToInt(
                        (
                            BodyShapeWaistLastFraction -
                            BodyShapeWaistFirstFraction) /
                        0.01f);
                if (work.ScanIndex <= count)
                {
                    float fraction =
                        BodyShapeWaistFirstFraction +
                        work.ScanIndex * 0.01f;
                    BodyShapeSection candidate;
                    if (TryBodyShapeSection(
                            work.Vertices,
                            work.Triangles,
                            work.Frame,
                            fraction *
                                work.Frame.TorsoLength,
                            Vector2.zero,
                            work.ScaleX,
                            work.ScaleZ,
                            out candidate) &&
                        (
                            work.Waist == null ||
                            candidate.Girth <
                                work.Waist.Girth))
                    {
                        work.Waist = candidate;
                        work.WaistFraction = fraction;
                    }
                    work.ScanIndex++;
                    return;
                }
                if (work.Waist == null)
                {
                    FailBodyShapeSignatureWork(work);
                    return;
                }
                work.Phase = 3;
                work.ScanIndex = 0;
                return;
            }
            if (work.Phase == 3)
            {
                int count =
                    Mathf.RoundToInt(
                        (
                            BodyShapeSeatLastFraction -
                            BodyShapeSeatFirstFraction) /
                        0.01f);
                if (work.ScanIndex <= count)
                {
                    float fraction =
                        BodyShapeSeatFirstFraction +
                        work.ScanIndex * 0.01f;
                    BodyShapeSection candidate;
                    if (TryBodyShapeSection(
                            work.Vertices,
                            work.Triangles,
                            work.Frame,
                            fraction *
                                work.Frame.TorsoLength,
                            Vector2.zero,
                            work.ScaleX,
                            work.ScaleZ,
                            out candidate) &&
                        (
                            work.Seat == null ||
                            candidate.MinimumZ <
                                work.Seat.MinimumZ))
                    {
                        work.Seat = candidate;
                        work.SeatFraction = fraction;
                    }
                    work.ScanIndex++;
                    return;
                }
                if (work.Seat == null)
                {
                    FailBodyShapeSignatureWork(work);
                    return;
                }
                work.Phase = 4;
                work.ScanIndex = 0;
                return;
            }

            List<BodyShapeLoop> thighLoops =
                BuildBodyShapeLoops(
                    work.Vertices,
                    work.Triangles,
                    work.Frame,
                    -BodyShapeUpperThighLegFraction *
                        work.Frame.HipToKnee,
                    work.ScaleX,
                    work.ScaleZ);
            BodyShapeLoop leftLoop =
                SelectBodyShapeThighLoop(
                    thighLoops,
                    true,
                    work.Frame,
                    work.ScaleX,
                    work.ScaleZ);
            BodyShapeLoop rightLoop =
                SelectBodyShapeThighLoop(
                    thighLoops,
                    false,
                    work.Frame,
                    work.ScaleX,
                    work.ScaleZ);
            List<BodyShapeLoop> leftLoops =
                new List<BodyShapeLoop>();
            List<BodyShapeLoop> rightLoops =
                new List<BodyShapeLoop>();
            if (leftLoop != null)
            {
                leftLoops.Add(leftLoop);
            }
            if (rightLoop != null)
            {
                rightLoops.Add(rightLoop);
            }
            if (!TryBodyShapeSectionFromLoops(
                    leftLoops,
                    Vector2.zero,
                    null,
                    work.ScaleX,
                    work.ScaleZ,
                    out work.LeftThigh,
                    out leftLoop) ||
                !TryBodyShapeSectionFromLoops(
                    rightLoops,
                    Vector2.zero,
                    null,
                    work.ScaleX,
                    work.ScaleZ,
                    out work.RightThigh,
                    out rightLoop))
            {
                FailBodyShapeSignatureWork(work);
                return;
            }
            float meanGirth =
                (
                    work.LeftThigh.Girth +
                    work.RightThigh.Girth) * 0.5f;
            if (Mathf.Abs(
                    work.LeftThigh.Girth -
                    work.RightThigh.Girth) /
                    Mathf.Max(meanGirth, 0.00000001f) >
                0.35f)
            {
                FailBodyShapeSignatureWork(work);
                return;
            }
            work.Result = BuildBodyShapeWorkResult(work);
            work.Complete = true;
            work.Failed = work.Result == null;
        }

        private static JSONClass BodyShapeMetricJson(
            BodyShapeMetric metric,
            float structuralLength)
        {
            JSONClass result = new JSONClass();
            result["meters"].AsFloat = metric.Meters;
            result["ratio"].AsFloat =
                metric.Meters / structuralLength;
            result["confidence"].AsFloat = 1.0f;
            if (metric.Bilateral)
            {
                result["leftMeters"].AsFloat =
                    metric.LeftMeters;
                result["rightMeters"].AsFloat =
                    metric.RightMeters;
            }
            return result;
        }

        private static JSONClass BodyShapeRegionJson()
        {
            JSONClass result = new JSONClass();
            result["geometryConfidence"].AsFloat = 1.0f;
            result["evidenceConfidence"].AsFloat = 1.0f;
            result["confidence"].AsFloat = 1.0f;
            return result;
        }

        private static JSONClass BuildBodyShapeJson(
            BodyShapeSignature signature)
        {
            if (!IsValidBodyShapeSignature(signature))
            {
                return null;
            }
            JSONClass result = new JSONClass();
            result["schema"].AsInt = 1;
            result["space"] = "mhr-neutral-bind";
            JSONClass normalizer = new JSONClass();
            normalizer["id"] = "structural-length";
            normalizer["meters"].AsFloat =
                signature.StructuralLength;
            result["normalizer"] = normalizer;
            result["confidenceKind"] =
                "heuristic-evidence-consistency";
            JSONClass measurements = new JSONClass();
            int index;
            for (index = 0;
                 index < BodyShapeMetricNames.Length;
                 index++)
            {
                string name = BodyShapeMetricNames[index];
                measurements[name] =
                    BodyShapeMetricJson(
                        signature.Measurements[name],
                        signature.StructuralLength);
            }
            result["measurements"] = measurements;
            JSONClass regions = new JSONClass();
            regions["breasts"] = BodyShapeRegionJson();
            regions["waist"] = BodyShapeRegionJson();
            regions["hips"] = BodyShapeRegionJson();
            regions["glutes"] = BodyShapeRegionJson();
            regions["thighs"] = BodyShapeRegionJson();
            result["regions"] = regions;
            JSONClass planes = new JSONClass();
            planes["bustTorsoFraction"].AsFloat =
                signature.BustTorsoFraction;
            planes["underbustTorsoFraction"].AsFloat =
                signature.UnderbustTorsoFraction;
            planes["waistTorsoFraction"].AsFloat =
                signature.WaistTorsoFraction;
            planes["seatTorsoFraction"].AsFloat =
                signature.SeatTorsoFraction;
            planes["upperThighLegFraction"].AsFloat =
                signature.UpperThighLegFraction;
            result["planes"] = planes;
            result["overallConfidence"].AsFloat = 1.0f;
            return result;
        }

        private static float BodyShapeCalibrationStep(
            BodyProportionMorphEntry entry)
        {
            if (entry == null)
            {
                return 0f;
            }
            float positive =
                entry.Maximum - entry.Value;
            if (positive > 0.0001f)
            {
                return Mathf.Min(
                    BodyShapeResponseStep,
                    positive);
            }
            float negative =
                entry.Minimum - entry.Value;
            if (negative < -0.0001f)
            {
                return Mathf.Max(
                    -BodyShapeResponseStep,
                    negative);
            }
            return 0f;
        }

        private static void PopulateBodyShapeResponses(
            DAZCharacterSelector geometry,
            BodyShapeSignature baseline,
            List<BodyProportionMorphEntry> entries)
        {
            if (!IsValidBodyShapeSignature(baseline) ||
                entries == null)
            {
                return;
            }
            DAZSkinV2 skin;
            Vector3[] vertices;
            int[] triangles;
            if (!TryBodyShapeMesh(
                    geometry,
                    out skin,
                    out vertices,
                    out triangles))
            {
                return;
            }
            Vector3[] scratch =
                new Vector3[vertices.Length];
            int entryIndex;
            for (entryIndex = 0;
                 entryIndex < entries.Count;
                 entryIndex++)
            {
                BodyProportionMorphEntry entry =
                    entries[entryIndex];
                if (entry == null ||
                    entry.Morph == null ||
                    entry.FitKind != "shape" ||
                    !IsBodyShapeCalibrationMorphName(entry.Name) ||
                    entry.Morph.hasBoneModificationFormulas)
                {
                    continue;
                }
                float step = BodyShapeCalibrationStep(entry);
                if (Mathf.Abs(step) <= 0.0001f)
                {
                    continue;
                }
                try
                {
                    entry.Morph.LoadDeltas();
                    DAZMorphVertex[] deltas =
                        entry.Morph.deltas;
                    if (deltas == null || deltas.Length == 0)
                    {
                        continue;
                    }
                    Array.Copy(
                        vertices,
                        scratch,
                        vertices.Length);
                    int applied = 0;
                    int deltaIndex;
                    for (deltaIndex = 0;
                         deltaIndex < deltas.Length;
                         deltaIndex++)
                    {
                        DAZMorphVertex delta =
                            deltas[deltaIndex];
                        if (delta.vertex < 0 ||
                            delta.vertex >= scratch.Length ||
                            !IsFiniteBodyProportionPoint(
                                delta.delta))
                        {
                            continue;
                        }
                        scratch[delta.vertex] +=
                            delta.delta * step;
                        applied++;
                    }
                    if (applied == 0)
                    {
                        continue;
                    }
                    BodyShapeSignature sampled;
                    if (!TryBuildBodyShapeSignature(
                            geometry,
                            scratch,
                            out sampled))
                    {
                        continue;
                    }
                    Dictionary<string, float> responses =
                        new Dictionary<string, float>();
                    int metricIndex;
                    for (metricIndex = 0;
                         metricIndex <
                            BodyShapeMetricNames.Length;
                         metricIndex++)
                    {
                        string name =
                            BodyShapeMetricNames[metricIndex];
                        float baselineRatio =
                            baseline.Measurements[name].Meters /
                            baseline.StructuralLength;
                        float sampledRatio =
                            sampled.Measurements[name].Meters /
                            sampled.StructuralLength;
                        float response =
                            (
                                sampledRatio -
                                baselineRatio) / step;
                        if (IsFinite(response) &&
                            Mathf.Abs(response) <= 10.0f)
                        {
                            responses[name] = response;
                        }
                    }
                    if (responses.Count != 0)
                    {
                        entry.ShapeResponses = responses;
                    }
                }
                catch
                {
                    entry.ShapeResponses = null;
                }
            }
        }

        private bool IsCurrentBodyShapeBuild(
            PersonBodyShapeBuild build)
        {
            if (build == null ||
                build.Cancelled ||
                build.Atom == null)
            {
                return false;
            }
            PersonBodyShapeBuild current = null;
            return
                _personBodyShapeBuilds.TryGetValue(
                    build.Atom.uid,
                    out current) &&
                object.ReferenceEquals(current, build);
        }

        private void RemoveBodyShapeBuild(
            PersonBodyShapeBuild build)
        {
            if (build == null || build.Atom == null)
            {
                return;
            }
            PersonBodyShapeBuild current = null;
            if (_personBodyShapeBuilds.TryGetValue(
                    build.Atom.uid,
                    out current) &&
                object.ReferenceEquals(current, build))
            {
                _personBodyShapeBuilds.Remove(
                    build.Atom.uid);
            }
        }

        private void CancelPersonBodyShapeBuild(
            string atomUid)
        {
            if (atomUid == null || atomUid.Length == 0)
            {
                return;
            }
            PersonBodyShapeBuild build = null;
            if (_personBodyShapeBuilds.TryGetValue(
                    atomUid,
                    out build))
            {
                build.Cancelled = true;
                _personBodyShapeBuilds.Remove(atomUid);
            }
        }

        private IEnumerator BuildPersonBodyShapeCacheCoroutine(
            PersonBodyShapeBuild build)
        {
            BodyShapeSignatureWork baselineWork =
                CreateBodyShapeSignatureWork(
                    build.Vertices,
                    build.Triangles,
                    build.Frame,
                    build.ScaleX,
                    build.ScaleZ);
            if (baselineWork == null)
            {
                RemoveBodyShapeBuild(build);
                yield break;
            }
            while (!baselineWork.Complete)
            {
                float deadline =
                    Time.realtimeSinceStartup +
                    BodyShapeBuildFrameBudgetSeconds;
                int stepsThisFrame = 0;
                do
                {
                    if (!IsCurrentBodyShapeBuild(build))
                    {
                        yield break;
                    }
                    StepBodyShapeSignatureWork(
                        baselineWork);
                    stepsThisFrame++;
                }
                while (
                    !baselineWork.Complete &&
                    stepsThisFrame <
                        BodyShapeBuildMaximumStepsPerFrame &&
                    Time.realtimeSinceStartup < deadline);
                if (!baselineWork.Complete)
                {
                    yield return null;
                }
            }
            if (baselineWork.Failed ||
                baselineWork.Result == null ||
                !IsCurrentBodyShapeBuild(build))
            {
                RemoveBodyShapeBuild(build);
                yield break;
            }

            Dictionary<
                DAZMorph,
                Dictionary<string, float>> responses =
                new Dictionary<
                    DAZMorph,
                    Dictionary<string, float>>();
            Vector3[] scratch =
                new Vector3[build.Vertices.Length];
            int entryIndex;
            for (entryIndex = 0;
                 entryIndex < build.Entries.Count;
                 entryIndex++)
            {
                if (!IsCurrentBodyShapeBuild(build))
                {
                    yield break;
                }
                BodyProportionMorphEntry entry =
                    build.Entries[entryIndex];
                if (entry == null ||
                    entry.Morph == null ||
                    entry.FitKind != "shape" ||
                    !IsBodyShapeCalibrationMorphName(entry.Name) ||
                    entry.Morph.hasBoneModificationFormulas ||
                    !IsEligibleBodyProportionMorph(
                        entry.Bank,
                        entry.Morph) ||
                    Mathf.Abs(
                        entry.Morph.morphValue -
                        entry.Value) > 0.000001f)
                {
                    continue;
                }
                float step =
                    BodyShapeCalibrationStep(entry);
                if (Mathf.Abs(step) <= 0.0001f)
                {
                    continue;
                }
                DAZMorphVertex[] deltas = null;
                try
                {
                    entry.Morph.LoadDeltas();
                    deltas = entry.Morph.deltas;
                }
                catch
                {
                    deltas = null;
                }
                if (deltas == null || deltas.Length == 0)
                {
                    continue;
                }
                Array.Copy(
                    build.Vertices,
                    scratch,
                    build.Vertices.Length);
                int applied = 0;
                int deltaIndex;
                for (deltaIndex = 0;
                     deltaIndex < deltas.Length;
                     deltaIndex++)
                {
                    DAZMorphVertex delta =
                        deltas[deltaIndex];
                    if (delta.vertex < 0 ||
                        delta.vertex >= scratch.Length ||
                        !IsFiniteBodyProportionPoint(
                            delta.delta))
                    {
                        continue;
                    }
                    scratch[delta.vertex] +=
                        delta.delta * step;
                    applied++;
                }
                if (applied == 0)
                {
                    continue;
                }
                BodyShapeSignatureWork sampledWork =
                    CreateBodyShapeSignatureWork(
                        scratch,
                        build.Triangles,
                        build.Frame,
                        build.ScaleX,
                        build.ScaleZ);
                if (sampledWork == null)
                {
                    continue;
                }
                yield return null;
                while (!sampledWork.Complete)
                {
                    float deadline =
                        Time.realtimeSinceStartup +
                        BodyShapeBuildFrameBudgetSeconds;
                    int stepsThisFrame = 0;
                    do
                    {
                        if (!IsCurrentBodyShapeBuild(build))
                        {
                            yield break;
                        }
                        StepBodyShapeSignatureWork(
                            sampledWork);
                        stepsThisFrame++;
                    }
                    while (
                        !sampledWork.Complete &&
                        stepsThisFrame <
                            BodyShapeBuildMaximumStepsPerFrame &&
                        Time.realtimeSinceStartup < deadline);
                    if (!sampledWork.Complete)
                    {
                        yield return null;
                    }
                }
                if (sampledWork.Failed ||
                    sampledWork.Result == null)
                {
                    continue;
                }
                Dictionary<string, float> morphResponses =
                    new Dictionary<string, float>();
                int metricIndex;
                for (metricIndex = 0;
                     metricIndex <
                        BodyShapeMetricNames.Length;
                     metricIndex++)
                {
                    string name =
                        BodyShapeMetricNames[metricIndex];
                    float baselineRatio =
                        baselineWork.Result.
                            Measurements[name].Meters /
                        baselineWork.Result.
                            StructuralLength;
                    float sampledRatio =
                        sampledWork.Result.
                            Measurements[name].Meters /
                        sampledWork.Result.
                            StructuralLength;
                    float response =
                        (
                            sampledRatio -
                            baselineRatio) / step;
                    if (IsFinite(response) &&
                        Mathf.Abs(response) <= 10.0f)
                    {
                        morphResponses[name] = response;
                    }
                }
                if (morphResponses.Count != 0)
                {
                    responses[entry.Morph] =
                        morphResponses;
                }
                yield return null;
            }

            if (!IsCurrentBodyShapeBuild(build))
            {
                yield break;
            }
            string currentChecksum = "";
            if (!TryBodyShapeMeshChecksum(
                    build.Geometry,
                    out currentChecksum) ||
                !string.Equals(
                    currentChecksum,
                    build.MeshChecksum,
                    StringComparison.Ordinal))
            {
                RemoveBodyShapeBuild(build);
                yield break;
            }
            PersonBodyShapeCache cache =
                new PersonBodyShapeCache();
            cache.Atom = build.Atom;
            cache.Geometry = build.Geometry;
            cache.MeshChecksum = build.MeshChecksum;
            cache.Signature = baselineWork.Result;
            cache.Responses = responses;
            _personBodyShapeCaches[
                build.Atom.uid] = cache;
            RemoveBodyShapeBuild(build);
            PublishSceneStatus();
        }

        private void EnsurePersonBodyShapeBuild(
            Atom atom,
            DAZCharacterSelector geometry,
            string meshChecksum,
            List<BodyProportionMorphEntry> entries)
        {
            if (atom == null ||
                geometry == null ||
                meshChecksum == null ||
                meshChecksum.Length == 0)
            {
                return;
            }
            PersonBodyShapeCache cache = null;
            if (_personBodyShapeCaches.TryGetValue(
                    atom.uid,
                    out cache) &&
                object.ReferenceEquals(cache.Atom, atom) &&
                object.ReferenceEquals(
                    cache.Geometry,
                    geometry) &&
                string.Equals(
                    cache.MeshChecksum,
                    meshChecksum,
                    StringComparison.Ordinal) &&
                IsValidBodyShapeSignature(
                    cache.Signature))
            {
                return;
            }
            _personBodyShapeCaches.Remove(atom.uid);
            PersonBodyShapeBuild existing = null;
            if (_personBodyShapeBuilds.TryGetValue(
                    atom.uid,
                    out existing))
            {
                if (object.ReferenceEquals(
                        existing.Atom,
                        atom) &&
                    object.ReferenceEquals(
                        existing.Geometry,
                        geometry) &&
                    string.Equals(
                        existing.MeshChecksum,
                        meshChecksum,
                        StringComparison.Ordinal))
                {
                    return;
                }
                existing.Cancelled = true;
            }

            DAZSkinV2 skin;
            Vector3[] liveVertices;
            int[] liveTriangles;
            BodyShapeFrame frame;
            if (!TryBodyShapeMesh(
                    geometry,
                    out skin,
                    out liveVertices,
                    out liveTriangles) ||
                !TryBuildBodyShapeFrame(
                    geometry,
                    skin,
                    out frame))
            {
                return;
            }
            float scaleX =
                skin.transform.TransformVector(
                    frame.Lateral).magnitude;
            float scaleZ =
                skin.transform.TransformVector(
                    frame.Front).magnitude;
            if (!IsFinite(scaleX) ||
                !IsFinite(scaleZ) ||
                scaleX <= 0.000001f ||
                scaleZ <= 0.000001f)
            {
                return;
            }
            PersonBodyShapeBuild build =
                new PersonBodyShapeBuild();
            build.Atom = atom;
            build.Geometry = geometry;
            build.MeshChecksum = meshChecksum;
            build.Vertices =
                new Vector3[liveVertices.Length];
            Array.Copy(
                liveVertices,
                build.Vertices,
                liveVertices.Length);
            build.Triangles =
                new int[liveTriangles.Length];
            Array.Copy(
                liveTriangles,
                build.Triangles,
                liveTriangles.Length);
            build.Frame = frame;
            build.ScaleX = scaleX;
            build.ScaleZ = scaleZ;
            build.Entries =
                new List<BodyProportionMorphEntry>();
            if (entries != null)
            {
                int index;
                for (index = 0;
                     index < entries.Count;
                     index++)
                {
                    if (entries[index] != null &&
                        entries[index].FitKind == "shape" &&
                        IsBodyShapeCalibrationMorphName(
                            entries[index].Name))
                    {
                        build.Entries.Add(entries[index]);
                    }
                }
            }
            _personBodyShapeBuilds[atom.uid] =
                build;
            StartCoroutine(
                BuildPersonBodyShapeCacheCoroutine(
                    build));
        }

        private static void CopyBodyShapeResponsesFromCache(
            List<BodyProportionMorphEntry> entries,
            PersonBodyShapeCache cache)
        {
            if (entries == null ||
                cache == null ||
                cache.Responses == null)
            {
                return;
            }
            int index;
            for (index = 0; index < entries.Count; index++)
            {
                BodyProportionMorphEntry entry =
                    entries[index];
                Dictionary<string, float> response = null;
                if (entry != null &&
                    entry.Morph != null &&
                    entry.FitKind == "shape" &&
                    cache.Responses.TryGetValue(
                        entry.Morph,
                        out response))
                {
                    entry.ShapeResponses = response;
                }
            }
        }

        private static JSONClass BuildBodyProportionMeasurements(
            DAZCharacterSelector geometry)
        {
            JSONClass result = new JSONClass();
            result["schema"].AsInt = 1;
            result["space"] = "vam-morphed-neutral-bind";
            JSONClass measurements = new JSONClass();
            result["measurements"] = measurements;

            DAZBone leftShoulder =
                BodyProportionBone(geometry, "lShldr", "lShoulder");
            DAZBone rightShoulder =
                BodyProportionBone(geometry, "rShldr", "rShoulder");
            DAZBone leftForearm =
                BodyProportionBone(geometry, "lForeArm", "lForearm");
            DAZBone rightForearm =
                BodyProportionBone(geometry, "rForeArm", "rForearm");
            DAZBone leftHand =
                geometry == null ? null : geometry.leftHandBone;
            if (leftHand == null)
            {
                leftHand =
                    BodyProportionBone(geometry, "lHand");
            }
            DAZBone rightHand =
                geometry == null ? null : geometry.rightHandBone;
            if (rightHand == null)
            {
                rightHand =
                    BodyProportionBone(geometry, "rHand");
            }
            DAZBone leftThigh =
                BodyProportionBone(geometry, "lThigh");
            DAZBone rightThigh =
                BodyProportionBone(geometry, "rThigh");
            DAZBone leftShin =
                BodyProportionBone(geometry, "lShin");
            DAZBone rightShin =
                BodyProportionBone(geometry, "rShin");
            DAZBone leftFoot =
                geometry == null ? null : geometry.leftFootBone;
            if (leftFoot == null)
            {
                leftFoot =
                    BodyProportionBone(geometry, "lFoot");
            }
            DAZBone rightFoot =
                geometry == null ? null : geometry.rightFootBone;
            if (rightFoot == null)
            {
                rightFoot =
                    BodyProportionBone(geometry, "rFoot");
            }
            DAZBone head =
                geometry == null ? null : geometry.headBone;
            if (head == null)
            {
                head = BodyProportionBone(geometry, "head");
            }

            float structuralHeight = 0f;
            bool hasStructuralHeight = false;
            if (head != null &&
                (leftFoot != null || rightFoot != null))
            {
                Vector3 headPoint = head.morphedWorldPosition;
                Vector3 feetPoint =
                    leftFoot != null && rightFoot != null
                    ? (
                        leftFoot.morphedWorldPosition +
                        rightFoot.morphedWorldPosition) * 0.5f
                    : leftFoot != null
                    ? leftFoot.morphedWorldPosition
                    : rightFoot.morphedWorldPosition;
                if (IsFiniteBodyProportionPoint(headPoint) &&
                    IsFiniteBodyProportionPoint(feetPoint))
                {
                    structuralHeight =
                        Mathf.Abs(headPoint.y - feetPoint.y);
                    hasStructuralHeight =
                        IsFinite(structuralHeight) &&
                        structuralHeight > 0.000001f;
                }
            }
            JSONClass normalizer = new JSONClass();
            normalizer["id"] = "structuralHeight";
            normalizer["available"].AsBool =
                hasStructuralHeight;
            if (hasStructuralHeight)
            {
                normalizer["meters"].AsFloat =
                    structuralHeight;
            }
            else
            {
                normalizer["reason"] =
                    "Head-to-foot neutral-bind joints are unavailable.";
            }
            result["normalizer"] = normalizer;
            measurements["structuralHeight"] =
                hasStructuralHeight
                ? BodyProportionMeasurement(
                    structuralHeight,
                    structuralHeight,
                    "head-joint-to-foot-joint-y")
                : UnavailableBodyProportionMeasurement(
                    "Head-to-foot neutral-bind joints are unavailable.");

            measurements["upperArm"] =
                PairedBodyProportionMeasurement(
                    leftShoulder,
                    leftForearm,
                    rightShoulder,
                    rightForearm,
                    structuralHeight,
                    "shoulder-joint-to-forearm-joint");
            measurements["forearm"] =
                PairedBodyProportionMeasurement(
                    leftForearm,
                    leftHand,
                    rightForearm,
                    rightHand,
                    structuralHeight,
                    "forearm-joint-to-hand-joint");
            measurements["thigh"] =
                PairedBodyProportionMeasurement(
                    leftThigh,
                    leftShin,
                    rightThigh,
                    rightShin,
                    structuralHeight,
                    "thigh-joint-to-shin-joint");
            measurements["shin"] =
                PairedBodyProportionMeasurement(
                    leftShin,
                    leftFoot,
                    rightShin,
                    rightFoot,
                    structuralHeight,
                    "shin-joint-to-foot-joint");

            float distance;
            measurements["torso"] =
                TryBodyProportionMidpointDistance(
                    leftShoulder,
                    rightShoulder,
                    leftThigh,
                    rightThigh,
                    out distance)
                ? BodyProportionMeasurement(
                    distance,
                    structuralHeight,
                    "shoulder-midpoint-to-thigh-root-midpoint")
                : UnavailableBodyProportionMeasurement(
                    "Shoulder or thigh-root neutral-bind joints are unavailable.");
            measurements["shoulderSpan"] =
                TryBodyProportionDistance(
                    leftShoulder,
                    rightShoulder,
                    out distance)
                ? BodyProportionMeasurement(
                    distance,
                    structuralHeight,
                    "left-to-right-shoulder-joint")
                : UnavailableBodyProportionMeasurement(
                    "Both shoulder neutral-bind joints are required.");
            measurements["hipSpan"] =
                TryBodyProportionDistance(
                    leftThigh,
                    rightThigh,
                    out distance)
                ? BodyProportionMeasurement(
                    distance,
                    structuralHeight,
                    "left-to-right-thigh-root-joint")
                : UnavailableBodyProportionMeasurement(
                    "Both thigh-root neutral-bind joints are required.");
            return result;
        }

        private JSONClass BuildPersonBodyProportionStatus(
            Atom atom,
            bool selected)
        {
            JSONClass result = new JSONClass();
            result["schema"].AsInt = 1;
            result["selectedOnly"].AsBool = true;
            result["ready"].AsBool = false;
            result["revision"] = "";
            result["undoAvailable"].AsBool = false;
            result["undoPending"].AsBool = false;
            result["undoRevision"] = "";
            result["blockedBySam3d"].AsBool =
                _sam3dUndoSnapshot != null;
            result["bodyShapeReady"].AsBool = false;
            result["bodyShapePreparing"].AsBool = false;
            JSONArray publishedMorphs = new JSONArray();
            result["morphs"] = publishedMorphs;
            JSONClass limits = new JSONClass();
            limits["maxMorphs"].AsInt =
                MaximumBodyProportionMorphs;
            limits["maxChanges"].AsInt =
                MaximumBodyProportionChanges;
            limits["maxAbsoluteValue"].AsFloat =
                MaximumBodyProportionMagnitude;
            limits["maxDeltaPerRequest"].AsFloat =
                MaximumBodyProportionDelta;
            result["limits"] = limits;

            if (atom == null || atom.type != "Person" || !selected)
            {
                result["reason"] =
                    "Select this Person to publish its body proportions.";
                if (atom != null)
                {
                    _personBodyProportionSnapshots.Remove(atom.uid);
                    CancelPersonBodyShapeBuild(atom.uid);
                }
                return result;
            }
            DAZCharacterSelector geometry =
                atom.GetStorableByID("geometry")
                as DAZCharacterSelector;
            if (geometry == null)
            {
                result["reason"] =
                    "The selected Person has no native geometry.";
                _personBodyProportionSnapshots.Remove(atom.uid);
                _personBodyProportionUndo.Remove(atom.uid);
                _personBodyShapeCaches.Remove(atom.uid);
                CancelPersonBodyShapeBuild(atom.uid);
                return result;
            }

            JSONClass measurementSignature =
                BuildBodyProportionMeasurements(geometry);
            result["space"] =
                (string)measurementSignature["space"] ?? "";
            result["normalizer"] =
                measurementSignature["normalizer"];
            result["measurements"] =
                measurementSignature["measurements"];
            PersonBodyProportionSnapshot snapshot = null;
            bool priorSnapshotAvailable =
                _personBodyProportionSnapshots.TryGetValue(
                    atom.uid,
                    out snapshot) &&
                object.ReferenceEquals(snapshot.Atom, atom) &&
                object.ReferenceEquals(
                    snapshot.Geometry,
                    geometry);
            string bodyShapeMeshChecksum = "";
            bool hasBodyShapeMeshChecksum =
                TryBodyShapeMeshChecksum(
                    geometry,
                    out bodyShapeMeshChecksum);
            List<BodyProportionMorphEntry> entries =
                GetBodyProportionMorphEntries(geometry);
            PersonBodyShapeCache bodyShapeCache = null;
            bool bodyShapeReady =
                hasBodyShapeMeshChecksum &&
                _personBodyShapeCaches.TryGetValue(
                    atom.uid,
                    out bodyShapeCache) &&
                object.ReferenceEquals(
                    bodyShapeCache.Atom,
                    atom) &&
                object.ReferenceEquals(
                    bodyShapeCache.Geometry,
                    geometry) &&
                string.Equals(
                    bodyShapeCache.MeshChecksum,
                    bodyShapeMeshChecksum,
                    StringComparison.Ordinal) &&
                IsValidBodyShapeSignature(
                    bodyShapeCache.Signature);
            BodyShapeSignature bodyShape =
                bodyShapeReady
                ? bodyShapeCache.Signature
                : null;
            if (bodyShapeReady)
            {
                CopyBodyShapeResponsesFromCache(
                    entries,
                    bodyShapeCache);
            }
            else if (hasBodyShapeMeshChecksum)
            {
                EnsurePersonBodyShapeBuild(
                    atom,
                    geometry,
                    bodyShapeMeshChecksum,
                    entries);
            }
            PersonBodyShapeBuild bodyShapeBuild = null;
            bool bodyShapePreparing =
                !bodyShapeReady &&
                hasBodyShapeMeshChecksum &&
                _personBodyShapeBuilds.TryGetValue(
                    atom.uid,
                    out bodyShapeBuild) &&
                object.ReferenceEquals(
                    bodyShapeBuild.Atom,
                    atom) &&
                object.ReferenceEquals(
                    bodyShapeBuild.Geometry,
                    geometry) &&
                string.Equals(
                    bodyShapeBuild.MeshChecksum,
                    bodyShapeMeshChecksum,
                    StringComparison.Ordinal);
            result["bodyShapeReady"].AsBool =
                bodyShapeReady;
            result["bodyShapePreparing"].AsBool =
                bodyShapePreparing;
            if (bodyShapeReady)
            {
                result["bodyShape"] =
                    BuildBodyShapeJson(bodyShape);
            }
            else
            {
                result["bodyShapeReason"] =
                    bodyShapePreparing
                    ? "Neutral body-shape measurements are being prepared."
                    : "The neutral morphed body mesh could not be measured.";
            }
            string generationKey =
                BuildBodyProportionGenerationKey(
                    geometry,
                    entries,
                    bodyShape,
                    bodyShapeMeshChecksum);
            string morphStateKey =
                BuildBodyProportionMorphStateKey(
                    geometry,
                    entries);
            bool reuse =
                priorSnapshotAvailable &&
                IsCurrentBodyProportionSnapshot(
                    snapshot,
                    entries,
                    generationKey);
            if (!reuse)
            {
                snapshot =
                    new PersonBodyProportionSnapshot();
                snapshot.Revision =
                    Guid.NewGuid().ToString("N");
                snapshot.Entries =
                    new List<BodyProportionMorphEntry>();
                int newIndex;
                for (newIndex = 0;
                     newIndex < entries.Count;
                     newIndex++)
                {
                    entries[newIndex].Key =
                        Guid.NewGuid().ToString("N");
                    snapshot.Entries.Add(entries[newIndex]);
                }
            }
            else
            {
                int reuseIndex;
                for (reuseIndex = 0;
                     reuseIndex < entries.Count;
                     reuseIndex++)
                {
                    entries[reuseIndex].Key =
                        snapshot.Entries[reuseIndex].Key;
                    entries[reuseIndex].ShapeResponses =
                        snapshot.Entries[
                            reuseIndex].ShapeResponses;
                }
                snapshot.Entries = entries;
            }
            snapshot.Atom = atom;
            snapshot.Geometry = geometry;
            snapshot.GenerationKey = generationKey;
            snapshot.BodyShape = bodyShape;
            snapshot.BodyShapeMeshChecksum =
                bodyShapeMeshChecksum;
            _personBodyProportionSnapshots[atom.uid] =
                snapshot;

            int index;
            for (index = 0; index < snapshot.Entries.Count; index++)
            {
                BodyProportionMorphEntry entry =
                    snapshot.Entries[index];
                JSONClass published = new JSONClass();
                published["key"] = entry.Key;
                published["name"] = entry.Name;
                published["region"] = entry.Region;
                published["fitKind"] = entry.FitKind;
                if (entry.FitKind == "shape")
                {
                    published["shapeRegion"] =
                        entry.ShapeRegion;
                    if (entry.ShapeResponses != null)
                    {
                        JSONClass responses =
                            new JSONClass();
                        int responseIndex;
                        for (responseIndex = 0;
                             responseIndex <
                                BodyShapeMetricNames.Length;
                             responseIndex++)
                        {
                            string responseName =
                                BodyShapeMetricNames[
                                    responseIndex];
                            float response;
                            if (entry.ShapeResponses.TryGetValue(
                                    responseName,
                                    out response))
                            {
                                responses[
                                    responseName].AsFloat =
                                    response;
                            }
                        }
                        published["shapeResponses"] =
                            responses;
                    }
                }
                published["value"].AsFloat = entry.Value;
                published["min"].AsFloat = entry.Minimum;
                published["max"].AsFloat = entry.Maximum;
                published["builtIn"].AsBool = true;
                publishedMorphs.Add(published);
            }

            PersonBodyProportionUndo undo = null;
            bool undoRecordAvailable =
                _personBodyProportionUndo.TryGetValue(
                    atom.uid,
                    out undo) &&
                object.ReferenceEquals(undo.Atom, atom) &&
                object.ReferenceEquals(
                    undo.Geometry,
                    geometry) &&
                undo.Values != null &&
                undo.Values.Count != 0;
            bool undoAvailable = false;
            bool undoPending = false;
            if (undoRecordAvailable)
            {
                undoAvailable =
                    string.Equals(
                        undo.PostApplyMorphStateKey,
                        morphStateKey,
                        StringComparison.Ordinal);
            }
            if (!undoRecordAvailable ||
                (
                    !undoAvailable &&
                    !undoPending))
            {
                _personBodyProportionUndo.Remove(atom.uid);
            }
            result["ready"].AsBool = entries.Count != 0;
            result["revision"] = snapshot.Revision;
            result["undoAvailable"].AsBool = undoAvailable;
            result["undoPending"].AsBool = undoPending;
            result["undoRevision"] =
                undoAvailable ? undo.Revision : "";
            result["morphCount"].AsInt = entries.Count;
            if (entries.Count == 0)
            {
                result["reason"] =
                    "No eligible built-in body-proportion morphs are available.";
            }
            return result;
        }

        private static string BuildPersonClothingGenerationKey(
            DAZCharacterSelector geometry,
            List<ActiveClothingEntry> entries)
        {
            ulong first = 1469598103934665603UL;
            ulong second = 7809847782465536322UL;
            HashCuaText(
                ref first,
                ref second,
                geometry == null ? "" : geometry.gender.ToString());
            HashCuaText(
                ref first,
                ref second,
                entries == null ? "-1" : entries.Count.ToString());
            if (entries != null)
            {
                int index;
                for (index = 0; index < entries.Count; index++)
                {
                    ActiveClothingEntry entry = entries[index];
                    if (entry.ResourceRef.Length != 0)
                    {
                        HashCuaText(
                            ref first,
                            ref second,
                            entry.ResourceRef);
                    }
                    else
                    {
                        HashCuaText(ref first, ref second, entry.Uid);
                        HashCuaText(
                            ref first,
                            ref second,
                            entry.InternalUid);
                        HashCuaText(
                            ref first,
                            ref second,
                            entry.PackageUid);
                    }
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.DisplayName);
                    int tagIndex;
                    for (tagIndex = 0;
                         tagIndex < entry.Tags.Length;
                         tagIndex++)
                    {
                        HashCuaText(
                            ref first,
                            ref second,
                            entry.Tags[tagIndex]);
                    }
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.Locked ? "locked" : "unlocked");
                }
            }
            return first.ToString("x16") + second.ToString("x16");
        }

        private JSONClass BuildPersonClothingStatus(
            Atom atom,
            ref int globalResourceBudget)
        {
            JSONClass clothing = new JSONClass();
            DAZCharacterSelector geometry =
                atom == null
                ? null
                : atom.GetStorableByID("geometry") as DAZCharacterSelector;
            clothing["ready"].AsBool = geometry != null;
            clothing["gender"] =
                geometry == null ? "None" : geometry.gender.ToString();
            JSONArray activeRefs = new JSONArray();
            JSONArray lockedRefs = new JSONArray();
            JSONArray activeItems = new JSONArray();
            clothing["activeResourceRefs"] = activeRefs;
            clothing["lockedResourceRefs"] = lockedRefs;
            clothing["activeItems"] = activeItems;
            clothing["activeCount"].AsInt = 0;
            clothing["lockedCount"].AsInt = 0;
            clothing["truncated"].AsBool = false;
            clothing["revision"] = "";
            if (geometry == null)
            {
                _personClothingSnapshots.Remove(atom.uid);
                return clothing;
            }

            List<ActiveClothingEntry> entries =
                GetActiveClothingEntries(atom, geometry);
            string generationKey =
                BuildPersonClothingGenerationKey(geometry, entries);
            PersonClothingSnapshot snapshot = null;
            bool reuse =
                _personClothingSnapshots.TryGetValue(
                    atom.uid,
                    out snapshot) &&
                object.ReferenceEquals(snapshot.Atom, atom) &&
                object.ReferenceEquals(snapshot.Geometry, geometry) &&
                string.Equals(
                    snapshot.GenerationKey,
                    generationKey,
                    StringComparison.Ordinal);
            if (!reuse)
            {
                snapshot = new PersonClothingSnapshot();
                snapshot.Revision = Guid.NewGuid().ToString("N");
            }
            snapshot.Atom = atom;
            snapshot.Geometry = geometry;
            snapshot.GenerationKey = generationKey;
            _personClothingSnapshots[atom.uid] = snapshot;

            HashSet<string> published =
                new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            int publishedItemCount = 0;
            int lockedCount = 0;
            int entryIndex;
            for (entryIndex = 0;
                 entryIndex < entries.Count;
                 entryIndex++)
            {
                ActiveClothingEntry entry = entries[entryIndex];
                if (entry.Locked)
                {
                    lockedCount++;
                }
                if (
                    publishedItemCount >= MaximumClothingRefsPerPerson ||
                    globalResourceBudget <= 0)
                {
                    continue;
                }
                JSONClass activeItem = new JSONClass();
                activeItem["displayName"] = entry.DisplayName;
                activeItem["tags"] = BuildRosterTags(entry.Tags);
                activeItem["locked"].AsBool = entry.Locked;
                activeItem["resourceRef"] = entry.ResourceRef;
                activeItems.Add(activeItem);
                publishedItemCount++;
                globalResourceBudget--;
                if (entry.ResourceRef.Length == 0 ||
                    !published.Add(entry.ResourceRef))
                {
                    continue;
                }
                activeRefs.Add(entry.ResourceRef);
                if (entry.Locked)
                {
                    lockedRefs.Add(entry.ResourceRef);
                }
            }
            clothing["activeCount"].AsInt = entries.Count;
            clothing["lockedCount"].AsInt = lockedCount;
            clothing["truncated"].AsBool =
                entries.Count > publishedItemCount;
            clothing["revision"] = snapshot.Revision;
            return clothing;
        }

        private static int CompareActiveHairEntries(
            ActiveHairEntry left,
            ActiveHairEntry right)
        {
            int displayOrder = string.Compare(
                left == null ? "" : left.DisplayName,
                right == null ? "" : right.DisplayName,
                StringComparison.OrdinalIgnoreCase);
            if (displayOrder != 0)
            {
                return displayOrder;
            }
            int packageOrder = string.Compare(
                left == null ? "" : left.PackageUid,
                right == null ? "" : right.PackageUid,
                StringComparison.Ordinal);
            if (packageOrder != 0)
            {
                return packageOrder;
            }
            return string.Compare(
                left == null ? "" : left.InternalUid,
                right == null ? "" : right.InternalUid,
                StringComparison.Ordinal);
        }

        private static List<ActiveHairEntry> GetActiveHairEntries(
            Atom atom,
            DAZCharacterSelector geometry)
        {
            List<ActiveHairEntry> result = new List<ActiveHairEntry>();
            if (atom == null || geometry == null || atom.type != "Person")
            {
                return result;
            }
            DAZHairGroup[] items =
                atom.GetComponentsInChildren<DAZHairGroup>();
            if (items == null)
            {
                return result;
            }
            int index;
            for (index = 0; index < items.Length; index++)
            {
                DAZHairGroup item = items[index];
                if (item == null || !item.active)
                {
                    continue;
                }
                ActiveHairEntry entry = new ActiveHairEntry();
                entry.Item = item;
                entry.Uid = item.uid ?? "";
                entry.InternalUid = item.internalUid ?? "";
                entry.PackageUid = item.packageUid ?? "";
                entry.DisplayName = SanitizeRosterText(
                    item.displayName,
                    MaximumRosterDisplayNameLength);
                if (entry.DisplayName.Length == 0)
                {
                    entry.DisplayName = "Unnamed hair item";
                }
                entry.Tags = SanitizeRosterTags(item.tagsArray);
                entry.Locked = item.locked;
                entry.Simulated =
                    item.GetComponentInChildren<HairSimControl>() != null;
                result.Add(entry);
            }
            result.Sort(CompareActiveHairEntries);
            return result;
        }

        private static string BuildPersonHairGenerationKey(
            DAZCharacterSelector geometry,
            List<ActiveHairEntry> entries)
        {
            ulong first = 1469598103934665603UL;
            ulong second = 7809847782465536322UL;
            HashCuaText(
                ref first,
                ref second,
                geometry == null ? "" : geometry.gender.ToString());
            HashCuaText(
                ref first,
                ref second,
                entries == null ? "-1" : entries.Count.ToString());
            if (entries != null)
            {
                int index;
                for (index = 0; index < entries.Count; index++)
                {
                    ActiveHairEntry entry = entries[index];
                    HashCuaText(ref first, ref second, entry.Uid);
                    HashCuaText(ref first, ref second, entry.InternalUid);
                    HashCuaText(ref first, ref second, entry.PackageUid);
                    HashCuaText(ref first, ref second, entry.DisplayName);
                    int tagIndex;
                    for (tagIndex = 0;
                         tagIndex < entry.Tags.Length;
                         tagIndex++)
                    {
                        HashCuaText(
                            ref first,
                            ref second,
                            entry.Tags[tagIndex]);
                    }
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.Locked ? "locked" : "unlocked");
                    HashCuaText(
                        ref first,
                        ref second,
                        entry.Simulated ? "simulated" : "mesh");
                }
            }
            return first.ToString("x16") + second.ToString("x16");
        }

        private JSONClass BuildPersonHairStatus(
            Atom atom,
            ref int globalItemBudget)
        {
            JSONClass hair = new JSONClass();
            DAZCharacterSelector geometry =
                atom == null
                ? null
                : atom.GetStorableByID("geometry") as DAZCharacterSelector;
            hair["ready"].AsBool = geometry != null;
            hair["activeCount"].AsInt = 0;
            hair["lockedCount"].AsInt = 0;
            hair["truncated"].AsBool = false;
            hair["revision"] = "";
            JSONArray publishedItems = new JSONArray();
            hair["items"] = publishedItems;
            if (geometry == null)
            {
                _personHairSnapshots.Remove(atom.uid);
                return hair;
            }

            List<ActiveHairEntry> entries =
                GetActiveHairEntries(atom, geometry);
            string generationKey =
                BuildPersonHairGenerationKey(geometry, entries);
            int publishableCount = Math.Min(
                entries.Count,
                Math.Min(
                    MaximumHairItemsPerPerson,
                    Math.Max(0, globalItemBudget)));
            PersonHairSnapshot snapshot = null;
            bool reuse =
                _personHairSnapshots.TryGetValue(
                    atom.uid,
                    out snapshot) &&
                object.ReferenceEquals(snapshot.Atom, atom) &&
                object.ReferenceEquals(snapshot.Geometry, geometry) &&
                string.Equals(
                    snapshot.GenerationKey,
                    generationKey,
                    StringComparison.Ordinal);
            if (reuse &&
                (snapshot.Items == null ||
                 snapshot.ActionTokens == null ||
                 snapshot.Items.Count != entries.Count ||
                 snapshot.ActionTokens.Count != entries.Count ||
                 snapshot.PublishedCount != publishableCount))
            {
                reuse = false;
            }
            if (reuse)
            {
                int identityIndex;
                for (identityIndex = 0;
                     identityIndex < entries.Count;
                     identityIndex++)
                {
                    if (!object.ReferenceEquals(
                            snapshot.Items[identityIndex],
                            entries[identityIndex].Item))
                    {
                        reuse = false;
                        break;
                    }
                }
            }
            if (!reuse)
            {
                snapshot = new PersonHairSnapshot();
                snapshot.Revision = Guid.NewGuid().ToString("N");
                snapshot.Items = new List<DAZHairGroup>();
                snapshot.ActionTokens = new List<string>();
                snapshot.PublishedCount = publishableCount;
                int tokenIndex;
                for (tokenIndex = 0;
                     tokenIndex < entries.Count;
                     tokenIndex++)
                {
                    snapshot.Items.Add(entries[tokenIndex].Item);
                    snapshot.ActionTokens.Add(
                        Guid.NewGuid().ToString("N"));
                }
            }
            snapshot.Atom = atom;
            snapshot.Geometry = geometry;
            snapshot.GenerationKey = generationKey;
            _personHairSnapshots[atom.uid] = snapshot;

            int lockedCount = 0;
            int publishedCount = 0;
            int entryIndex;
            for (entryIndex = 0;
                 entryIndex < entries.Count;
                 entryIndex++)
            {
                ActiveHairEntry entry = entries[entryIndex];
                if (entry.Locked)
                {
                    lockedCount++;
                }
                if (
                    entryIndex >= snapshot.PublishedCount)
                {
                    continue;
                }
                JSONClass publishedItem = new JSONClass();
                publishedItem["displayName"] = entry.DisplayName;
                publishedItem["tags"] = BuildRosterTags(entry.Tags);
                publishedItem["locked"].AsBool = entry.Locked;
                publishedItem["simulated"].AsBool = entry.Simulated;
                publishedItem["actionToken"] =
                    snapshot.ActionTokens[entryIndex];
                publishedItems.Add(publishedItem);
                publishedCount++;
                globalItemBudget--;
            }
            hair["activeCount"].AsInt = entries.Count;
            hair["lockedCount"].AsInt = lockedCount;
            hair["truncated"].AsBool = entries.Count > publishedCount;
            hair["revision"] = snapshot.Revision;
            return hair;
        }

        private JSONClass BuildCuaStatus(
            Atom atom,
            ref int globalChoiceBudget)
        {
            CuaLoaderState state = new CuaLoaderState();
            ResolveCuaLoader(atom, state);

            JSONArray publishedChoices = new JSONArray();
            List<int> publishedIndices = new List<int>();
            int eligibleCount = 0;
            int selectedIndex = -1;
            if (state.AssetName != null && state.AssetName.choices != null)
            {
                int index;
                for (index = 0;
                     index < state.AssetName.choices.Count;
                     index++)
                {
                    string rawChoice = state.AssetName.choices[index];
                    if (selectedIndex < 0 &&
                        string.Equals(
                            state.AssetName.val,
                            rawChoice,
                            StringComparison.Ordinal))
                    {
                        selectedIndex = index;
                    }
                    if (!IsEligibleCuaChoice(rawChoice))
                    {
                        continue;
                    }
                    eligibleCount++;
                    if (publishedIndices.Count >= MaximumCuaChoicesPerAtom ||
                        globalChoiceBudget <= 0)
                    {
                        continue;
                    }

                    JSONClass publishedChoice = new JSONClass();
                    publishedChoice["index"].AsInt = index;
                    publishedChoice["label"] =
                        SanitizeCuaChoiceLabel(rawChoice);
                    publishedChoices.Add(publishedChoice);
                    publishedIndices.Add(index);
                    globalChoiceBudget--;
                }
            }

            string generationKey =
                BuildCuaGenerationKey(
                    state.AssetUrl,
                    state.AssetName,
                    publishedIndices);
            CuaChoiceSnapshot snapshot = null;
            bool reuse =
                _cuaChoiceSnapshots.TryGetValue(atom.uid, out snapshot) &&
                object.ReferenceEquals(snapshot.Atom, atom) &&
                object.ReferenceEquals(snapshot.Loader, state.Loader) &&
                object.ReferenceEquals(
                    snapshot.ChoiceList,
                    state.AssetName == null
                    ? null
                    : state.AssetName.choices) &&
                string.Equals(
                    snapshot.GenerationKey,
                    generationKey,
                    StringComparison.Ordinal);
            if (!reuse)
            {
                snapshot = new CuaChoiceSnapshot();
                snapshot.ChoiceToken = Guid.NewGuid().ToString("N");
            }
            snapshot.Atom = atom;
            snapshot.Loader = state.Loader;
            snapshot.ChoiceList =
                state.AssetName == null ? null : state.AssetName.choices;
            snapshot.GenerationKey = generationKey;
            snapshot.PublishedIndices = publishedIndices;
            _cuaChoiceSnapshots[atom.uid] = snapshot;

            bool ready =
                state.Loader != null &&
                state.Error.Length == 0 &&
                state.Loader.isAssetLoaded;
            JSONClass cua = new JSONClass();
            cua["loadDll"].AsBool =
                state.LoadDll == null || state.LoadDll.val;
            cua["ready"].AsBool = ready;
            cua["isAssetLoaded"].AsBool = ready;
            cua["choiceToken"] = snapshot.ChoiceToken;
            cua["choiceCount"].AsInt = eligibleCount;
            cua["selectedIndex"].AsInt = selectedIndex;
            cua["choices"] = publishedChoices;
            cua["choicesTruncated"].AsBool =
                eligibleCount > publishedIndices.Count;
            return cua;
        }

        private static string SanitizeTimelineText(
            string value,
            int maximumLength)
        {
            if (value == null)
            {
                return "";
            }
            char[] characters = value.ToCharArray();
            int index;
            for (index = 0; index < characters.Length; index++)
            {
                if (characters[index] < ' ' ||
                    characters[index] == '\u007f')
                {
                    characters[index] = ' ';
                }
            }
            string result = new string(characters).Trim();
            if (result.Length > maximumLength)
            {
                result = result.Substring(0, maximumLength);
            }
            return result;
        }

        private static float BoundedTimelineFloat(
            float value,
            float minimum,
            float maximum,
            float fallback)
        {
            if (!IsFinite(value))
            {
                return fallback;
            }
            return Mathf.Clamp(value, minimum, maximum);
        }

        private static TimelineItemSnapshot FindTimelineItemByAdapterId(
            List<TimelineItemSnapshot> items,
            int adapterId)
        {
            if (items == null)
            {
                return null;
            }
            int index;
            for (index = 0; index < items.Count; index++)
            {
                TimelineItemSnapshot item = items[index];
                if (item != null && item.AdapterId == adapterId)
                {
                    return item;
                }
            }
            return null;
        }

        private static string TimelineTokenForAdapterId(
            List<TimelineItemSnapshot> items,
            int adapterId)
        {
            TimelineItemSnapshot item =
                FindTimelineItemByAdapterId(items, adapterId);
            return item == null ? "" : item.Token;
        }

        private static string ReuseTimelineItemToken(
            List<TimelineItemSnapshot> previousItems,
            int adapterId)
        {
            TimelineItemSnapshot previous =
                FindTimelineItemByAdapterId(previousItems, adapterId);
            return previous == null
                ? Guid.NewGuid().ToString("N")
                : previous.Token;
        }

        private static JSONArray TimelineControls(bool enhanced)
        {
            JSONArray controls = new JSONArray();
            controls.Add("play");
            controls.Add("pause");
            controls.Add("stop");
            controls.Add("reset");
            controls.Add("nextFrame");
            controls.Add("previousFrame");
            controls.Add("selectClip");
            controls.Add("playClip");
            if (enhanced)
            {
                controls.Add("selectSegment");
                controls.Add("selectLayer");
            }
            controls.Add("setTime");
            controls.Add("setSpeed");
            controls.Add("setWeight");
            controls.Add("setLocked");
            return controls;
        }

        private static JSONArray BasicTimelineControls(
            MVRScript plugin,
            bool hasPublishedClips)
        {
            JSONArray controls = new JSONArray();
            if (plugin.GetAction("Play If Not Playing") != null)
                controls.Add("play");
            if (plugin.GetBoolJSONParam("Paused") != null)
                controls.Add("pause");
            if (plugin.GetAction("Stop If Playing") != null)
                controls.Add("stop");
            if (plugin.GetAction("Stop And Reset") != null)
                controls.Add("reset");
            if (plugin.GetAction("Next Frame") != null)
                controls.Add("nextFrame");
            if (plugin.GetAction("Previous Frame") != null)
                controls.Add("previousFrame");
            if (hasPublishedClips)
            {
                controls.Add("selectClip");
                if (plugin.GetAction("Play Current Clip") != null)
                    controls.Add("playClip");
            }
            if (plugin.GetFloatJSONParam("Set Time") != null)
                controls.Add("setTime");
            if (plugin.GetFloatJSONParam("Speed") != null)
                controls.Add("setSpeed");
            if (plugin.GetFloatJSONParam("Weight") != null)
                controls.Add("setWeight");
            if (plugin.GetBoolJSONParam("Locked") != null)
                controls.Add("setLocked");
            return controls;
        }

        private TimelineSnapshot CreateTimelineSnapshot(
            string key,
            Atom atom,
            MVRScript plugin,
            string storableId,
            string generationKey,
            bool enhanced,
            int catalogRevision,
            out TimelineSnapshot previousForTokens)
        {
            TimelineSnapshot previous = null;
            _timelineSnapshots.TryGetValue(key, out previous);
            bool sameIdentity =
                previous != null &&
                object.ReferenceEquals(previous.Atom, atom) &&
                object.ReferenceEquals(previous.Plugin, plugin);
            bool sameGeneration =
                sameIdentity &&
                string.Equals(
                    previous.GenerationKey,
                    generationKey,
                    StringComparison.Ordinal);
            previousForTokens = sameGeneration ? previous : null;

            TimelineSnapshot snapshot = new TimelineSnapshot();
            snapshot.Atom = atom;
            snapshot.Plugin = plugin;
            snapshot.StorableId = storableId;
            snapshot.TimelineId =
                sameIdentity
                ? previous.TimelineId
                : Guid.NewGuid().ToString("N");
            snapshot.Revision =
                sameGeneration
                ? previous.Revision
                : Guid.NewGuid().ToString("N");
            snapshot.GenerationKey = generationKey;
            snapshot.Enhanced = enhanced;
            snapshot.CatalogRevision = catalogRevision;
            snapshot.Segments = new List<TimelineItemSnapshot>();
            snapshot.Layers = new List<TimelineItemSnapshot>();
            snapshot.Clips = new List<TimelineItemSnapshot>();
            _timelineSnapshots[key] = snapshot;
            return snapshot;
        }

        private static JSONClass TimelineItemJson(
            TimelineItemSnapshot item,
            string segmentToken,
            string layerToken,
            bool includeClipDetails)
        {
            JSONClass result = new JSONClass();
            result["id"] = item.Token;
            result["name"] = item.Name;
            result["selected"].AsBool = item.Selected;
            if (segmentToken.Length != 0)
            {
                result["segmentId"] = segmentToken;
            }
            if (includeClipDetails)
            {
                if (layerToken.Length != 0)
                {
                    result["layerId"] = layerToken;
                }
                result["qualified"] = item.Qualified;
                result["length"].AsFloat = item.Length;
                result["loop"].AsBool = item.Loop;
                result["playing"].AsBool = item.Playing;
                result["main"].AsBool = item.Main;
                result["time"].AsFloat = item.Time;
                result["speed"].AsFloat = item.Speed;
                result["weight"].AsFloat = item.Weight;
                result["targetCount"].AsInt = item.TargetCount;
            }
            return result;
        }

        private static int BoundedTimelineCount(int value)
        {
            if (value < 0)
            {
                return 0;
            }
            return Math.Min(value, 1000000);
        }

        private static int TimelineStateCount(
            JSONClass state,
            string key,
            int fallback)
        {
            JSONClass counts =
                state == null ? null : state["counts"].AsObject;
            if (counts == null || !counts.HasKey(key))
            {
                return BoundedTimelineCount(fallback);
            }
            return BoundedTimelineCount(counts[key].AsInt);
        }

        private static int TimelineStateLimit(
            JSONClass state,
            string key,
            int fallback)
        {
            JSONClass limits =
                state == null ? null : state["limits"].AsObject;
            int value =
                limits == null || !limits.HasKey(key)
                ? fallback
                : BoundedTimelineCount(limits[key].AsInt);
            if (value <= 0)
            {
                value = fallback;
            }
            return Math.Min(value, fallback);
        }

        private static JSONClass TimelineLimitsJson(
            JSONClass state,
            int allocatedClips)
        {
            JSONClass limits = new JSONClass();
            limits["maxSegments"].AsInt =
                TimelineStateLimit(
                    state,
                    "maxSegments",
                    MaximumTimelineSegments);
            limits["maxLayers"].AsInt =
                TimelineStateLimit(
                    state,
                    "maxLayers",
                    MaximumTimelineLayers);
            limits["maxClips"].AsInt =
                TimelineStateLimit(
                    state,
                    "maxClips",
                    MaximumTimelineClips);
            limits["maxClipsGlobally"].AsInt =
                MaximumTimelineClipsGlobally;
            limits["allocatedClips"].AsInt =
                Math.Max(
                    0,
                    Math.Min(
                        allocatedClips,
                        MaximumTimelineClips));
            return limits;
        }

        private static string SanitizeTimelineErrorCode(string value)
        {
            value = (value ?? "").Trim().ToLowerInvariant();
            string result = "";
            int index;
            for (index = 0;
                 index < value.Length && result.Length < 64;
                 index++)
            {
                char character = value[index];
                if ((character >= 'a' && character <= 'z') ||
                    (character >= '0' && character <= '9') ||
                    character == '-')
                {
                    result += character;
                }
            }
            return result;
        }

        private static JSONClass TimelineAdapterErrorJson(
            JSONClass state)
        {
            JSONClass source =
                state == null ? null : state["error"].AsObject;
            if (source == null)
            {
                return null;
            }
            string code =
                SanitizeTimelineErrorCode((string)source["code"]);
            string message =
                SanitizeTimelineText(
                    (string)source["message"],
                    500);
            if (code.Length == 0 && message.Length == 0)
            {
                return null;
            }
            JSONClass error = new JSONClass();
            error["code"] =
                code.Length == 0 ? "adapter-error" : code;
            error["message"] =
                message.Length == 0
                ? "Timeline adapter reported an error."
                : message;
            return error;
        }

        private static JSONClass TimelineAdapterErrorJson(
            string code,
            string message)
        {
            JSONClass state = new JSONClass();
            JSONClass error = new JSONClass();
            error["code"] = code;
            error["message"] = message;
            state["error"] = error;
            return TimelineAdapterErrorJson(state);
        }

        private JSONClass BuildEnhancedTimelineStatus(
            string key,
            Atom atom,
            MVRScript plugin,
            string storableId,
            JSONClass state,
            bool selected,
            int clipBudget)
        {
            int catalogRevision =
                Math.Max(0, state["catalogRevision"].AsInt);
            JSONArray rawSegments = state["segments"].AsArray;
            JSONArray rawLayers = state["layers"].AsArray;
            JSONArray rawClips = state["clips"].AsArray;
            int clipLimit =
                rawClips == null
                ? 0
                : Math.Min(
                    rawClips.Count,
                    Math.Min(
                        MaximumTimelineClips,
                        Math.Max(0, clipBudget)));
            string generationKey =
                "adapter:" +
                catalogRevision +
                ":" +
                (rawSegments == null ? 0 : rawSegments.Count) +
                ":" +
                (rawLayers == null ? 0 : rawLayers.Count) +
                ":" +
                (rawClips == null ? 0 : rawClips.Count) +
                ":published:" +
                clipLimit;
            TimelineSnapshot previous;
            TimelineSnapshot snapshot =
                CreateTimelineSnapshot(
                    key,
                    atom,
                    plugin,
                    storableId,
                    generationKey,
                    true,
                    catalogRevision,
                    out previous);

            int index;
            int segmentLimit =
                rawSegments == null
                ? 0
                : Math.Min(rawSegments.Count, MaximumTimelineSegments);
            for (index = 0; index < segmentLimit; index++)
            {
                JSONClass source = rawSegments[index].AsObject;
                if (source == null)
                {
                    continue;
                }
                if (!source.HasKey("id"))
                {
                    continue;
                }
                int adapterId = source["id"].AsInt;
                if (adapterId < 0 ||
                    FindTimelineItemByAdapterId(
                        snapshot.Segments,
                        adapterId) != null)
                {
                    continue;
                }
                TimelineItemSnapshot item =
                    new TimelineItemSnapshot();
                item.Token = ReuseTimelineItemToken(
                    previous == null ? null : previous.Segments,
                    adapterId);
                item.AdapterId = adapterId;
                item.AdapterSegmentId = adapterId;
                item.AdapterLayerId = -1;
                item.Name = SanitizeTimelineText(
                    (string)source["name"],
                    MaximumTimelineLabelLength);
                item.RawName = item.Name;
                snapshot.Segments.Add(item);
            }

            int layerLimit =
                rawLayers == null
                ? 0
                : Math.Min(rawLayers.Count, MaximumTimelineLayers);
            for (index = 0; index < layerLimit; index++)
            {
                JSONClass source = rawLayers[index].AsObject;
                if (source == null)
                {
                    continue;
                }
                if (!source.HasKey("id") ||
                    !source.HasKey("segmentId"))
                {
                    continue;
                }
                int adapterId = source["id"].AsInt;
                int segmentId = source["segmentId"].AsInt;
                if (adapterId < 0 ||
                    FindTimelineItemByAdapterId(
                        snapshot.Layers,
                        adapterId) != null ||
                    FindTimelineItemByAdapterId(
                        snapshot.Segments,
                        segmentId) == null)
                {
                    continue;
                }
                TimelineItemSnapshot item =
                    new TimelineItemSnapshot();
                item.Token = ReuseTimelineItemToken(
                    previous == null ? null : previous.Layers,
                    adapterId);
                item.AdapterId = adapterId;
                item.AdapterSegmentId = segmentId;
                item.AdapterLayerId = adapterId;
                item.Name = SanitizeTimelineText(
                    (string)source["name"],
                    MaximumTimelineLabelLength);
                item.RawName = item.Name;
                snapshot.Layers.Add(item);
            }

            for (index = 0; index < clipLimit; index++)
            {
                JSONClass source = rawClips[index].AsObject;
                if (source == null)
                {
                    continue;
                }
                if (!source.HasKey("id") ||
                    !source.HasKey("segmentId") ||
                    !source.HasKey("layerId"))
                {
                    continue;
                }
                int adapterId = source["id"].AsInt;
                int segmentId = source["segmentId"].AsInt;
                int layerId = source["layerId"].AsInt;
                if (adapterId < 0 ||
                    FindTimelineItemByAdapterId(
                        snapshot.Clips,
                        adapterId) != null ||
                    FindTimelineItemByAdapterId(
                        snapshot.Segments,
                        segmentId) == null ||
                    FindTimelineItemByAdapterId(
                        snapshot.Layers,
                        layerId) == null)
                {
                    continue;
                }
                TimelineItemSnapshot item =
                    new TimelineItemSnapshot();
                item.Token = ReuseTimelineItemToken(
                    previous == null ? null : previous.Clips,
                    adapterId);
                item.AdapterId = adapterId;
                item.AdapterSegmentId = segmentId;
                item.AdapterLayerId = layerId;
                item.Name = SanitizeTimelineText(
                    (string)source["name"],
                    MaximumTimelineLabelLength);
                item.RawName = item.Name;
                item.Qualified = SanitizeTimelineText(
                    (string)source["qualified"],
                    MaximumTimelineQualifiedLength);
                item.Length = BoundedTimelineFloat(
                    source["length"].AsFloat,
                    0f,
                    86400f,
                    0f);
                item.Time = BoundedTimelineFloat(
                    source["time"].AsFloat,
                    0f,
                    86400f,
                    0f);
                item.Speed = BoundedTimelineFloat(
                    source["speed"].AsFloat,
                    -1f,
                    5f,
                    1f);
                item.Weight = BoundedTimelineFloat(
                    source["weight"].AsFloat,
                    0f,
                    1f,
                    1f);
                item.TargetCount =
                    BoundedTimelineCount(
                        source["targetCount"].AsInt);
                item.Loop = source["loop"].AsBool;
                item.Playing = source["playing"].AsBool;
                item.Main = source["main"].AsBool;
                item.Selected = source["selected"].AsBool;
                snapshot.Clips.Add(item);
            }

            JSONClass currentSource = state["current"].AsObject;
            int currentClipId =
                currentSource == null
                ? -1
                : currentSource["clipId"].AsInt;
            int currentSegmentId =
                currentSource == null
                ? -1
                : currentSource["segmentId"].AsInt;
            int currentLayerId =
                currentSource == null
                ? -1
                : currentSource["layerId"].AsInt;
            TimelineItemSnapshot currentClip =
                FindTimelineItemByAdapterId(
                    snapshot.Clips,
                    currentClipId);
            TimelineItemSnapshot currentSegment =
                FindTimelineItemByAdapterId(
                    snapshot.Segments,
                    currentSegmentId);
            TimelineItemSnapshot currentLayer =
                FindTimelineItemByAdapterId(
                    snapshot.Layers,
                    currentLayerId);
            if (currentClip != null)
            {
                currentClip.Selected = true;
            }
            if (currentSegment != null)
            {
                currentSegment.Selected = true;
            }
            if (currentLayer != null)
            {
                currentLayer.Selected = true;
            }

            JSONClass result = new JSONClass();
            result["id"] = snapshot.TimelineId;
            result["revision"] = snapshot.Revision;
            result["atomUid"] =
                SanitizeTimelineText(atom.uid, 200);
            string customLabel = "";
            if (plugin.pluginLabelJSON != null)
            {
                customLabel = SanitizeTimelineText(
                    plugin.pluginLabelJSON.val,
                    MaximumTimelineLabelLength);
            }
            result["label"] =
                customLabel.Length == 0
                ? SanitizeTimelineText(
                    atom.name,
                    MaximumTimelineLabelLength)
                : SanitizeTimelineText(
                    atom.name + ": " + customLabel,
                    MaximumTimelineLabelLength);
            result["enhanced"].AsBool = true;
            result["adapterVersion"] = SanitizeTimelineText(
                (string)state["adapterVersion"],
                64);
            JSONClass adapterError =
                TimelineAdapterErrorJson(state);
            result["ready"].AsBool =
                state["ready"].AsBool && adapterError == null;
            result["selected"].AsBool = selected;
            result["stateSequence"].AsInt =
                BoundedTimelineCount(
                    state["stateSequence"].AsInt);

            JSONClass transportSource =
                state["transport"].AsObject;
            JSONClass transport = new JSONClass();
            if (transportSource != null)
            {
                transport["playing"].AsBool =
                    transportSource["playing"].AsBool;
                transport["paused"].AsBool =
                    transportSource["paused"].AsBool;
                transport["time"].AsFloat =
                    BoundedTimelineFloat(
                        transportSource["time"].AsFloat,
                        0f,
                        86400f,
                        0f);
                transport["clipTime"].AsFloat =
                    BoundedTimelineFloat(
                        transportSource["clipTime"].AsFloat,
                        0f,
                        86400f,
                        0f);
                transport["speed"].AsFloat =
                    BoundedTimelineFloat(
                        transportSource["speed"].AsFloat,
                        -1f,
                        5f,
                        1f);
                transport["weight"].AsFloat =
                    BoundedTimelineFloat(
                        transportSource["weight"].AsFloat,
                        0f,
                        1f,
                        1f);
                transport["locked"].AsBool =
                    transportSource["locked"].AsBool;
            }
            JSONStorableFloat legacyScrubber =
                plugin.GetFloatJSONParam("Scrubber");
            transport["duration"].AsFloat =
                currentClip != null
                ? currentClip.Length
                : legacyScrubber == null
                    ? 0f
                    : BoundedTimelineFloat(
                        legacyScrubber.max,
                        0f,
                        86400f,
                        0f);
            result["transport"] = transport;

            JSONClass current = new JSONClass();
            current["clipId"] =
                currentClip == null ? "" : currentClip.Token;
            current["segmentId"] =
                currentSegment == null ? "" : currentSegment.Token;
            current["layerId"] =
                currentLayer == null ? "" : currentLayer.Token;
            current["qualified"] = SanitizeTimelineText(
                currentSource == null
                ? ""
                : (string)currentSource["qualified"],
                MaximumTimelineQualifiedLength);
            current["name"] = SanitizeTimelineText(
                currentSource == null
                ? ""
                : (string)currentSource["name"],
                MaximumTimelineLabelLength);
            current["segment"] = SanitizeTimelineText(
                currentSource == null
                ? ""
                : (string)currentSource["segment"],
                MaximumTimelineLabelLength);
            current["layer"] = SanitizeTimelineText(
                currentSource == null
                ? ""
                : (string)currentSource["layer"],
                MaximumTimelineLabelLength);
            result["current"] = current;

            JSONArray segments = new JSONArray();
            for (index = 0; index < snapshot.Segments.Count; index++)
            {
                segments.Add(
                    TimelineItemJson(
                        snapshot.Segments[index],
                        "",
                        "",
                        false));
            }
            JSONArray layers = new JSONArray();
            for (index = 0; index < snapshot.Layers.Count; index++)
            {
                TimelineItemSnapshot item = snapshot.Layers[index];
                layers.Add(
                    TimelineItemJson(
                        item,
                        TimelineTokenForAdapterId(
                            snapshot.Segments,
                            item.AdapterSegmentId),
                        "",
                        false));
            }
            JSONArray clips = new JSONArray();
            for (index = 0; index < snapshot.Clips.Count; index++)
            {
                TimelineItemSnapshot item = snapshot.Clips[index];
                clips.Add(
                    TimelineItemJson(
                        item,
                        TimelineTokenForAdapterId(
                            snapshot.Segments,
                            item.AdapterSegmentId),
                        TimelineTokenForAdapterId(
                            snapshot.Layers,
                            item.AdapterLayerId),
                        true));
            }
            result["segments"] = segments;
            result["layers"] = layers;
            result["clips"] = clips;

            JSONClass countsSource = state["counts"].AsObject;
            JSONClass counts = new JSONClass();
            counts["segments"].AsInt =
                countsSource == null
                ? snapshot.Segments.Count
                : BoundedTimelineCount(
                    countsSource["segments"].AsInt);
            counts["layers"].AsInt =
                countsSource == null
                ? snapshot.Layers.Count
                : BoundedTimelineCount(
                    countsSource["layers"].AsInt);
            counts["clips"].AsInt =
                countsSource == null
                ? snapshot.Clips.Count
                : BoundedTimelineCount(
                    countsSource["clips"].AsInt);
            counts["publishedSegments"].AsInt =
                snapshot.Segments.Count;
            counts["publishedLayers"].AsInt =
                snapshot.Layers.Count;
            counts["publishedClips"].AsInt =
                snapshot.Clips.Count;
            result["counts"] = counts;
            result["limits"] =
                TimelineLimitsJson(state, clipLimit);

            JSONClass truncatedSource =
                state["truncated"].AsObject;
            JSONClass truncated = new JSONClass();
            truncated["segments"].AsBool =
                (truncatedSource != null &&
                 truncatedSource["segments"].AsBool) ||
                (rawSegments != null &&
                 rawSegments.Count > MaximumTimelineSegments);
            truncated["layers"].AsBool =
                (truncatedSource != null &&
                 truncatedSource["layers"].AsBool) ||
                (rawLayers != null &&
                 rawLayers.Count > MaximumTimelineLayers);
            truncated["clips"].AsBool =
                (truncatedSource != null &&
                 truncatedSource["clips"].AsBool) ||
                (rawClips != null &&
                 rawClips.Count > snapshot.Clips.Count) ||
                counts["clips"].AsInt >
                    snapshot.Clips.Count;
            result["truncated"] = truncated;
            if (adapterError != null)
            {
                result["error"] = adapterError;
            }
            result["controls"] =
                state["ready"].AsBool && adapterError == null
                ? TimelineControls(true)
                : new JSONArray();
            return result;
        }

        private JSONClass BuildBasicTimelineStatus(
            string key,
            Atom atom,
            MVRScript plugin,
            string storableId,
            bool selected,
            int clipBudget,
            bool adapterAvailable,
            JSONClass adapterState,
            JSONClass adapterError)
        {
            JSONStorableStringChooser animations =
                plugin.GetStringChooserJSONParam("Animation");
            JSONStorableStringChooser segmentsParam =
                plugin.GetStringChooserJSONParam("Segment");
            List<string> rawAnimations =
                animations == null ? null : animations.choices;
            List<string> rawSegments =
                segmentsParam == null ? null : segmentsParam.choices;
            int clipLimit =
                rawAnimations == null
                ? 0
                : Math.Min(
                    rawAnimations.Count,
                    Math.Min(
                        MaximumTimelineClips,
                        Math.Max(0, clipBudget)));
            string generationKey =
                "legacy:published:" + clipLimit;
            int index;
            if (rawAnimations != null)
            {
                int limit = Math.Min(
                    rawAnimations.Count,
                    MaximumTimelineClips);
                for (index = 0; index < limit; index++)
                {
                    string name =
                        SanitizeTimelineText(
                            rawAnimations[index],
                            MaximumTimelineQualifiedLength);
                    generationKey += "|c:" +
                        name.Length +
                        ":" +
                        name;
                }
            }
            if (rawSegments != null)
            {
                int limit = Math.Min(
                    rawSegments.Count,
                    MaximumTimelineSegments);
                for (index = 0; index < limit; index++)
                {
                    string name =
                        SanitizeTimelineText(
                            rawSegments[index],
                            MaximumTimelineQualifiedLength);
                    generationKey += "|s:" +
                        name.Length +
                        ":" +
                        name;
                }
            }

            TimelineSnapshot previous;
            TimelineSnapshot snapshot =
                CreateTimelineSnapshot(
                    key,
                    atom,
                    plugin,
                    storableId,
                    generationKey,
                    false,
                    0,
                    out previous);

            if (rawSegments != null)
            {
                int limit = Math.Min(
                    rawSegments.Count,
                    MaximumTimelineSegments);
                for (index = 0; index < limit; index++)
                {
                    string rawName = rawSegments[index] ?? "";
                    if (rawName.Length > MaximumTimelineQualifiedLength ||
                        ContainsControlCharacter(rawName))
                    {
                        continue;
                    }
                    TimelineItemSnapshot item =
                        new TimelineItemSnapshot();
                    item.Token = ReuseTimelineItemToken(
                        previous == null ? null : previous.Segments,
                        index);
                    item.AdapterId = index;
                    item.AdapterSegmentId = index;
                    item.AdapterLayerId = -1;
                    item.RawName = rawName;
                    item.Name = SanitizeTimelineText(
                        rawName,
                        MaximumTimelineLabelLength);
                    item.Selected =
                        segmentsParam != null &&
                        string.Equals(
                            segmentsParam.val,
                            rawName,
                            StringComparison.Ordinal);
                    snapshot.Segments.Add(item);
                }
            }
            if (rawAnimations != null)
            {
                int limit = clipLimit;
                for (index = 0; index < limit; index++)
                {
                    string rawName = rawAnimations[index] ?? "";
                    if (rawName.Length > MaximumTimelineQualifiedLength ||
                        ContainsControlCharacter(rawName))
                    {
                        continue;
                    }
                    TimelineItemSnapshot item =
                        new TimelineItemSnapshot();
                    item.Token = ReuseTimelineItemToken(
                        previous == null ? null : previous.Clips,
                        index);
                    item.AdapterId = index;
                    item.AdapterSegmentId = -1;
                    item.AdapterLayerId = -1;
                    item.RawName = rawName;
                    item.Name = SanitizeTimelineText(
                        rawName,
                        MaximumTimelineLabelLength);
                    item.Qualified = SanitizeTimelineText(
                        rawName,
                        MaximumTimelineQualifiedLength);
                    item.Speed = 1f;
                    item.Weight = 1f;
                    item.Selected =
                        animations != null &&
                        string.Equals(
                            animations.val,
                            rawName,
                            StringComparison.Ordinal);
                    snapshot.Clips.Add(item);
                }
            }

            JSONStorableBool isPlaying =
                plugin.GetBoolJSONParam("Is Playing");
            JSONStorableBool paused =
                plugin.GetBoolJSONParam("Paused");
            JSONStorableBool locked =
                plugin.GetBoolJSONParam("Locked");
            JSONStorableFloat time =
                plugin.GetFloatJSONParam("Set Time");
            JSONStorableFloat scrubber =
                plugin.GetFloatJSONParam("Scrubber");
            JSONStorableFloat speed =
                plugin.GetFloatJSONParam("Speed");
            JSONStorableFloat weight =
                plugin.GetFloatJSONParam("Weight");
            bool ready =
                plugin.isActiveAndEnabled &&
                animations != null &&
                isPlaying != null &&
                time != null &&
                plugin.GetAction("Play If Not Playing") != null &&
                plugin.GetAction("Stop If Playing") != null;

            JSONClass result = new JSONClass();
            result["id"] = snapshot.TimelineId;
            result["revision"] = snapshot.Revision;
            result["atomUid"] =
                SanitizeTimelineText(atom.uid, 200);
            string customLabel = "";
            if (plugin.pluginLabelJSON != null)
            {
                customLabel = SanitizeTimelineText(
                    plugin.pluginLabelJSON.val,
                    MaximumTimelineLabelLength);
            }
            result["label"] =
                customLabel.Length == 0
                ? SanitizeTimelineText(
                    atom.name,
                    MaximumTimelineLabelLength)
                : SanitizeTimelineText(
                    atom.name + ": " + customLabel,
                    MaximumTimelineLabelLength);
            result["enhanced"].AsBool = adapterAvailable;
            result["adapterVersion"] =
                adapterAvailable
                ? SanitizeTimelineText(
                    adapterState == null
                    ? ""
                    : (string)adapterState["adapterVersion"],
                    64)
                : "";
            result["ready"].AsBool = ready;
            result["selected"].AsBool = selected;
            result["stateSequence"].AsInt =
                adapterState == null
                ? 0
                : BoundedTimelineCount(
                    adapterState["stateSequence"].AsInt);

            JSONClass transport = new JSONClass();
            transport["playing"].AsBool =
                isPlaying != null && isPlaying.val;
            transport["paused"].AsBool =
                paused != null && paused.val;
            transport["time"].AsFloat =
                time == null
                ? 0f
                : BoundedTimelineFloat(
                    time.val,
                    0f,
                    86400f,
                    0f);
            transport["clipTime"].AsFloat =
                scrubber == null
                ? 0f
                : BoundedTimelineFloat(
                    scrubber.val,
                    0f,
                    86400f,
                    0f);
            transport["duration"].AsFloat =
                scrubber == null
                ? 0f
                : BoundedTimelineFloat(
                    scrubber.max,
                    0f,
                    86400f,
                    0f);
            transport["speed"].AsFloat =
                speed == null
                ? 1f
                : BoundedTimelineFloat(
                    speed.val,
                    -1f,
                    5f,
                    1f);
            transport["weight"].AsFloat =
                weight == null
                ? 1f
                : BoundedTimelineFloat(
                    weight.val,
                    0f,
                    1f,
                    1f);
            transport["locked"].AsBool =
                locked != null && locked.val;
            result["transport"] = transport;

            JSONClass current = new JSONClass();
            string currentClipToken = "";
            for (index = 0;
                 index < snapshot.Clips.Count;
                 index++)
            {
                if (snapshot.Clips[index].Selected)
                {
                    currentClipToken =
                        snapshot.Clips[index].Token;
                    break;
                }
            }
            current["clipId"] = currentClipToken;
            string currentSegmentToken = "";
            for (index = 0;
                 index < snapshot.Segments.Count;
                 index++)
            {
                if (snapshot.Segments[index].Selected)
                {
                    currentSegmentToken =
                        snapshot.Segments[index].Token;
                    break;
                }
            }
            current["segmentId"] = currentSegmentToken;
            current["layerId"] = "";
            JSONClass adapterCurrent =
                adapterState == null
                ? null
                : adapterState["current"].AsObject;
            string legacyAnimation =
                animations == null
                ? ""
                : SanitizeTimelineText(
                    animations.val,
                    MaximumTimelineQualifiedLength);
            string adapterQualified =
                adapterCurrent == null
                ? ""
                : SanitizeTimelineText(
                    (string)adapterCurrent["qualified"],
                    MaximumTimelineQualifiedLength);
            string adapterName =
                adapterCurrent == null
                ? ""
                : SanitizeTimelineText(
                    (string)adapterCurrent["name"],
                    MaximumTimelineLabelLength);
            string adapterSegment =
                adapterCurrent == null
                ? ""
                : SanitizeTimelineText(
                    (string)adapterCurrent["segment"],
                    MaximumTimelineLabelLength);
            string adapterLayer =
                adapterCurrent == null
                ? ""
                : SanitizeTimelineText(
                    (string)adapterCurrent["layer"],
                    MaximumTimelineLabelLength);
            current["qualified"] =
                adapterQualified.Length != 0
                ? adapterQualified
                : legacyAnimation;
            current["name"] =
                adapterName.Length != 0
                ? adapterName
                : SanitizeTimelineText(
                    animations == null ? "" : animations.val,
                    MaximumTimelineLabelLength);
            current["segment"] =
                adapterSegment.Length != 0
                ? adapterSegment
                : segmentsParam == null
                    ? ""
                    : SanitizeTimelineText(
                        segmentsParam.val,
                        MaximumTimelineLabelLength);
            current["layer"] = adapterLayer;
            result["current"] = current;

            JSONArray segments = new JSONArray();
            for (index = 0; index < snapshot.Segments.Count; index++)
            {
                segments.Add(
                    TimelineItemJson(
                        snapshot.Segments[index],
                        "",
                        "",
                        false));
            }
            JSONArray clips = new JSONArray();
            for (index = 0; index < snapshot.Clips.Count; index++)
            {
                clips.Add(
                    TimelineItemJson(
                        snapshot.Clips[index],
                        "",
                        "",
                        true));
            }
            result["segments"] = segments;
            result["layers"] = new JSONArray();
            result["clips"] = clips;

            int segmentCount =
                Math.Max(
                    rawSegments == null ? 0 : rawSegments.Count,
                    TimelineStateCount(
                        adapterState,
                        "segments",
                        rawSegments == null ? 0 : rawSegments.Count));
            int layerCount =
                TimelineStateCount(adapterState, "layers", 0);
            int clipCount =
                Math.Max(
                    rawAnimations == null ? 0 : rawAnimations.Count,
                    TimelineStateCount(
                        adapterState,
                        "clips",
                        rawAnimations == null ? 0 : rawAnimations.Count));
            JSONClass counts = new JSONClass();
            counts["segments"].AsInt =
                BoundedTimelineCount(segmentCount);
            counts["layers"].AsInt =
                BoundedTimelineCount(layerCount);
            counts["clips"].AsInt =
                BoundedTimelineCount(clipCount);
            counts["publishedSegments"].AsInt =
                snapshot.Segments.Count;
            counts["publishedLayers"].AsInt = 0;
            counts["publishedClips"].AsInt =
                snapshot.Clips.Count;
            result["counts"] = counts;
            result["limits"] =
                TimelineLimitsJson(
                    adapterState,
                    snapshot.Clips.Count);

            JSONClass truncated = new JSONClass();
            truncated["segments"].AsBool =
                segmentCount > snapshot.Segments.Count;
            truncated["layers"].AsBool =
                layerCount > 0;
            truncated["clips"].AsBool =
                clipCount > snapshot.Clips.Count;
            result["truncated"] = truncated;
            if (adapterError != null)
            {
                result["error"] = adapterError;
            }
            result["controls"] =
                ready
                ? BasicTimelineControls(
                    plugin,
                    snapshot.Clips.Count != 0)
                : new JSONArray();
            return result;
        }

        private static JSONClass BuildSam3dCameraStatus(Atom atom)
        {
            MVRScript renderer = FindSam3dRenderer(atom);
            if (renderer == null)
            {
                return null;
            }
            JSONClass result = new JSONClass();
            result["compatible"].AsBool = true;
            string status =
                (renderer.GetStringJSONParam(
                    Sam3dStatusParam).val ?? "")
                .Trim()
                .ToLowerInvariant();
            if (status != "idle" &&
                status != "rendering" &&
                status != "encoding" &&
                status != "succeeded" &&
                status != "failed")
            {
                status = "unknown";
            }
            result["status"] = status;
            JSONStorableFloat fov =
                renderer.GetFloatJSONParam("Flat Horizontal FOV");
            if (fov != null && IsFinite(fov.val))
            {
                result["flatHorizontalFov"].AsFloat = fov.val;
            }
            JSONStorableStringChooser aspect =
                renderer.GetStringChooserJSONParam("Aspect Ratio");
            JSONStorableStringChooser resolution =
                renderer.GetStringChooserJSONParam("Output Resolution");
            result["aspectRatio"] =
                aspect == null ? "" : aspect.val ?? "";
            result["outputResolution"] =
                resolution == null ? "" : resolution.val ?? "";
            return result;
        }

        private JSONClass BuildSam3dReferenceStatus()
        {
            JSONClass result = new JSONClass();
            Sam3dReferenceState state =
                CurrentSam3dReferenceState();
            bool active =
                state != null;
            result["active"].AsBool = active;
            result["atomUid"] =
                active
                ? Sam3dReferenceUid
                : "";
            result["jobId"] =
                active
                ? state.JobId ?? ""
                : "";
            result["jobRevision"] =
                active
                ? state.JobRevision ?? ""
                : "";
            result["solutionRevision"] =
                active
                ? state.SolutionRevision ?? ""
                : "";
            result["targetUid"] =
                active
                ? state.TargetUid ?? ""
                : "";
            result["cameraUid"] = "";
            result["sourceWidth"].AsInt =
                active
                ? state.SourceWidth
                : 0;
            result["sourceHeight"].AsInt =
                active
                ? state.SourceHeight
                : 0;
            bool poseAligned =
                active &&
                state.AlignedToPose;
            result["alignedToPose"].AsBool =
                poseAligned;
            result["mode"] =
                !active
                ? ""
                : poseAligned
                ? "pose-aligned"
                : "body-fit";
            result["state"] =
                active
                ? "ready"
                : "absent";
            result["message"] = "";
            return result;
        }

        private static JSONArray Capabilities()
        {
            JSONArray capabilities = new JSONArray();
            capabilities.Add("atom-roster");
            capabilities.Add("atom-select");
            capabilities.Add("atom-add");
            capabilities.Add("atom-preset-apply");
            capabilities.Add("subscene-load");
            capabilities.Add("custom-unity-asset-load");
            capabilities.Add("custom-unity-asset-choice");
            capabilities.Add("scene-load");
            capabilities.Add("person-roster");
            capabilities.Add("person-preset-apply");
            capabilities.Add("person-preset-appearance");
            capabilities.Add("person-preset-animation");
            capabilities.Add("person-preset-breast-physics");
            capabilities.Add("person-preset-clothing");
            capabilities.Add("person-preset-general");
            capabilities.Add("person-preset-glute-physics");
            capabilities.Add("person-preset-hair");
            capabilities.Add("person-preset-morphs");
            capabilities.Add("person-preset-plugins");
            capabilities.Add("person-preset-pose");
            capabilities.Add("person-preset-skin");
            capabilities.Add("person-clothing-item-toggle");
            capabilities.Add("person-hair-roster");
            capabilities.Add("person-hair-item-toggle");
            capabilities.Add("person-body-proportions-v1");
            capabilities.Add("person-body-proportion-measurements-v1");
            capabilities.Add("person-body-proportion-apply-v1");
            capabilities.Add("person-body-proportion-undo-v1");
            capabilities.Add("person-body-shape-v1");
            capabilities.Add("person-add");
            capabilities.Add("person-select");
            capabilities.Add("timeline-roster");
            capabilities.Add("timeline-transport");
            capabilities.Add("timeline-animation-play");
            capabilities.Add("timeline-adapter-v1");
            capabilities.Add("sam3d-apply-v1");
            capabilities.Add("sam3d-undo-v1");
            capabilities.Add("sam3d-capture-v1");
            capabilities.Add("sam3d-camera-vrfunscript-v1");
            capabilities.Add("sam3d-reference-v1");
            return capabilities;
        }

        private void PublishTimelineStatus()
        {
            try
            {
                JSONClass document = new JSONClass();
                document["protocol"].AsInt = ProtocolVersion;
                document["timelineProtocol"].AsInt =
                    TimelineProtocolVersion;
                document["bridgeVersion"] = BridgeVersion;
                document["instanceId"] = _instanceId;
                document["updatedAtUtc"] = UtcNow();

                SuperController controller = SuperController.singleton;
                bool loading = controller == null || controller.isLoading;
                document["loading"].AsBool = loading;
                Atom selected =
                    controller == null
                    ? null
                    : controller.GetSelectedAtom();

                List<TimelineCandidate> candidates =
                    new List<TimelineCandidate>();
                HashSet<string> liveKeys = new HashSet<string>();
                int discoveredCount = 0;
                if (controller != null)
                {
                    foreach (Atom atom in controller.GetAtoms())
                    {
                        if (atom == null)
                        {
                            continue;
                        }
                        List<string> storableIds =
                            atom.GetStorableIDs();
                        if (storableIds == null)
                        {
                            continue;
                        }
                        int idIndex;
                        for (idIndex = 0;
                             idIndex < storableIds.Count;
                             idIndex++)
                        {
                            string storableId =
                                storableIds[idIndex] ?? "";
                            if (!storableId.EndsWith(
                                    "VamTimeline.AtomPlugin",
                                    StringComparison.Ordinal))
                            {
                                continue;
                            }
                            MVRScript plugin =
                                atom.GetStorableByID(storableId)
                                as MVRScript;
                            if (plugin == null)
                            {
                                continue;
                            }
                            discoveredCount++;
                            if (candidates.Count >=
                                MaximumTimelineInstances)
                            {
                                continue;
                            }

                            string key =
                                (atom.uid ?? "") +
                                "\n" +
                                storableId;
                            liveKeys.Add(key);
                            bool isSelected =
                                selected != null &&
                                object.ReferenceEquals(selected, atom);
                            JSONStorableString adapterState =
                                plugin.GetStringJSONParam(
                                    TimelineExternalState);
                            JSONStorableAction refresh =
                                plugin.GetAction(
                                    TimelineRefreshExternalState);
                            JSONStorableString adapterCommand =
                                plugin.GetStringJSONParam(
                                    TimelineExternalCommand);
                            JSONStorableString adapterResult =
                                plugin.GetStringJSONParam(
                                    TimelineExternalResult);
                            JSONStorableAction execute =
                                plugin.GetAction(
                                    TimelineExecuteExternalCommand);

                            TimelineCandidate candidate =
                                new TimelineCandidate();
                            candidate.ScanIndex = candidates.Count;
                            candidate.Key = key;
                            candidate.Atom = atom;
                            candidate.Plugin = plugin;
                            candidate.StorableId = storableId;
                            candidate.Selected = isSelected;
                            JSONStorableBool isPlaying =
                                plugin.GetBoolJSONParam("Is Playing");
                            candidate.Playing =
                                isPlaying != null && isPlaying.val;
                            candidate.AdapterAvailable =
                                adapterState != null &&
                                refresh != null &&
                                refresh.actionCallback != null &&
                                adapterCommand != null &&
                                adapterResult != null &&
                                execute != null &&
                                execute.actionCallback != null;
                            candidate.AdapterState = adapterState;
                            candidate.AdapterRefresh = refresh;
                            candidates.Add(candidate);
                        }
                    }
                }

                List<TimelineCandidate> prioritized =
                    new List<TimelineCandidate>(candidates);
                prioritized.Sort(
                    delegate(
                        TimelineCandidate left,
                        TimelineCandidate right)
                    {
                        if (left.Selected != right.Selected)
                        {
                            return left.Selected ? -1 : 1;
                        }
                        if (left.Playing != right.Playing)
                        {
                            return left.Playing ? -1 : 1;
                        }
                        return left.ScanIndex.CompareTo(
                            right.ScanIndex);
                    });

                int globalClipBudget =
                    MaximumTimelineClipsGlobally;
                int totalClipCount = 0;
                int publishedClipCount = 0;
                bool enhancedFound = false;
                int candidateIndex;
                for (candidateIndex = 0;
                     candidateIndex < prioritized.Count;
                     candidateIndex++)
                {
                    TimelineCandidate candidate =
                        prioritized[candidateIndex];
                    int instanceClipBudget =
                        Math.Min(
                            globalClipBudget,
                            MaximumTimelineClips);
                    JSONClass instance = null;
                    JSONClass adapterState = null;
                    JSONClass adapterError = null;

                    if (candidate.AdapterAvailable)
                    {
                        enhancedFound = true;
                        if (instanceClipBudget > 0)
                        {
                            try
                            {
                                candidate.AdapterRefresh.actionCallback();
                                adapterState =
                                    JSON.Parse(
                                        candidate.AdapterState.val ?? "")
                                    .AsObject;
                                if (adapterState != null &&
                                    adapterState["protocol"].AsInt ==
                                        TimelineProtocolVersion)
                                {
                                    instance =
                                        BuildEnhancedTimelineStatus(
                                            candidate.Key,
                                            candidate.Atom,
                                            candidate.Plugin,
                                            candidate.StorableId,
                                            adapterState,
                                            candidate.Selected,
                                            instanceClipBudget);
                                }
                                else
                                {
                                    adapterError =
                                        TimelineAdapterErrorJson(
                                            "invalid-state",
                                            "Timeline returned an invalid external state.");
                                }
                            }
                            catch (Exception exception)
                            {
                                adapterError =
                                    TimelineAdapterErrorJson(
                                        "refresh-failed",
                                        "Timeline could not refresh its external state: " +
                                        DescribeException(exception));
                            }
                        }
                        else
                        {
                            // Reuse metadata already published by Timeline,
                            // but do not invoke the adapter's full catalog
                            // rebuild once the global clip budget is spent.
                            try
                            {
                                adapterState =
                                    JSON.Parse(
                                        candidate.AdapterState.val ?? "")
                                    .AsObject;
                                if (adapterState == null ||
                                    adapterState["protocol"].AsInt !=
                                        TimelineProtocolVersion)
                                {
                                    adapterState = null;
                                }
                            }
                            catch
                            {
                                adapterState = null;
                            }
                            adapterError =
                                TimelineAdapterErrorJson(adapterState);
                        }
                    }

                    if (instance == null)
                    {
                        instance =
                            BuildBasicTimelineStatus(
                                candidate.Key,
                                candidate.Atom,
                                candidate.Plugin,
                                candidate.StorableId,
                                candidate.Selected,
                                instanceClipBudget,
                                candidate.AdapterAvailable,
                                adapterState,
                                adapterError);
                    }
                    candidate.Result = instance;

                    JSONClass instanceCounts =
                        instance["counts"].AsObject;
                    int instanceTotal =
                        instanceCounts == null
                        ? 0
                        : BoundedTimelineCount(
                            instanceCounts["clips"].AsInt);
                    int instancePublished =
                        instanceCounts == null
                        ? 0
                        : BoundedTimelineCount(
                            instanceCounts[
                                "publishedClips"].AsInt);
                    totalClipCount += instanceTotal;
                    publishedClipCount += instancePublished;
                    globalClipBudget =
                        Math.Max(
                            0,
                            globalClipBudget -
                                instancePublished);
                }

                JSONArray instances = new JSONArray();
                for (candidateIndex = 0;
                     candidateIndex < candidates.Count;
                     candidateIndex++)
                {
                    instances.Add(candidates[candidateIndex].Result);
                }

                List<string> removedKeys = new List<string>();
                foreach (
                    KeyValuePair<string, TimelineSnapshot> entry
                    in _timelineSnapshots)
                {
                    if (!liveKeys.Contains(entry.Key))
                    {
                        removedKeys.Add(entry.Key);
                    }
                }
                int removedIndex;
                for (removedIndex = 0;
                     removedIndex < removedKeys.Count;
                     removedIndex++)
                {
                    _timelineSnapshots.Remove(removedKeys[removedIndex]);
                }

                JSONArray capabilities = new JSONArray();
                capabilities.Add("timeline-roster");
                capabilities.Add("timeline-transport");
                capabilities.Add("timeline-animation-play");
                if (enhancedFound)
                {
                    capabilities.Add("timeline-adapter-v1");
                }
                document["instances"] = instances;
                document["truncated"].AsBool =
                    discoveredCount > MaximumTimelineInstances ||
                    totalClipCount > publishedClipCount;
                JSONClass counts = new JSONClass();
                counts["instances"].AsInt =
                    BoundedTimelineCount(discoveredCount);
                counts["publishedInstances"].AsInt =
                    candidates.Count;
                counts["clips"].AsInt =
                    BoundedTimelineCount(totalClipCount);
                counts["publishedClips"].AsInt =
                    BoundedTimelineCount(publishedClipCount);
                document["counts"] = counts;
                JSONClass limits = new JSONClass();
                limits["maxInstances"].AsInt =
                    MaximumTimelineInstances;
                limits["maxClips"].AsInt =
                    MaximumTimelineClips;
                limits["maxClipsGlobally"].AsInt =
                    MaximumTimelineClipsGlobally;
                document["limits"] = limits;
                document["capabilities"] = capabilities;
                FileManagerSecure.WriteAllText(
                    TimelinePath,
                    document.ToString());
            }
            catch (Exception exception)
            {
                SuperController.LogError(
                    "[VAM-PIP Bridge] Could not write Timeline status: " +
                    DescribeException(exception));
            }
        }

        private void PublishSceneStatus()
        {
            try
            {
                JSONClass scene = new JSONClass();
                scene["protocol"].AsInt = ProtocolVersion;
                scene["bridgeVersion"] = BridgeVersion;
                scene["instanceId"] = _instanceId;
                scene["updatedAtUtc"] = UtcNow();

                SuperController controller = SuperController.singleton;
                bool loading = controller == null || controller.isLoading;
                scene["loading"].AsBool = loading;

                Atom selected = null;
                if (controller != null)
                {
                    selected = controller.GetSelectedAtom();
                }
                string selectedUid =
                    selected != null
                    ? selected.uid ?? ""
                    : "";
                scene["selectedUid"] = selectedUid;

                JSONArray atoms = new JSONArray();
                JSONArray persons = new JSONArray();
                int globalCuaChoiceBudget = MaximumCuaChoicesGlobally;
                int globalClothingResourceBudget =
                    MaximumClothingRefsGlobally;
                int globalHairItemBudget =
                    MaximumHairItemsGlobally;
                HashSet<string> liveCuaUids = new HashSet<string>();
                HashSet<string> livePersonUids = new HashSet<string>();
                if (controller != null)
                {
                    foreach (Atom atom in controller.GetAtoms())
                    {
                        if (atom == null)
                        {
                            continue;
                        }
                        bool isSelected =
                            selectedUid.Length != 0 &&
                            atom.uid == selectedUid;
                        JSONClass atomStatus = new JSONClass();
                        atomStatus["uid"] = atom.uid ?? "";
                        atomStatus["type"] = atom.type ?? "";
                        atomStatus["selected"].AsBool = isSelected;
                        if (atom.type == "CustomUnityAsset")
                        {
                            liveCuaUids.Add(atom.uid);
                            atomStatus["cua"] =
                                BuildCuaStatus(
                                    atom,
                                    ref globalCuaChoiceBudget);
                        }
                        if (atom.type == "Empty")
                        {
                            JSONClass sam3dCamera =
                                BuildSam3dCameraStatus(atom);
                            if (sam3dCamera != null)
                            {
                                atomStatus["sam3dCamera"] =
                                    sam3dCamera;
                            }
                        }
                        atoms.Add(atomStatus);

                        if (atom.type != "Person")
                        {
                            continue;
                        }
                        JSONClass person = new JSONClass();
                        person["uid"] = atom.uid ?? "";
                        person["selected"].AsBool = isSelected;
                        livePersonUids.Add(atom.uid);
                        person["clothing"] =
                            BuildPersonClothingStatus(
                                atom,
                                ref globalClothingResourceBudget);
                        person["hair"] =
                            BuildPersonHairStatus(
                                atom,
                                ref globalHairItemBudget);
                        person["bodyProportions"] =
                            BuildPersonBodyProportionStatus(
                                atom,
                                isSelected);
                        persons.Add(person);
                    }
                }
                List<string> removedCuaUids = new List<string>();
                foreach (
                    KeyValuePair<string, CuaChoiceSnapshot> entry
                    in _cuaChoiceSnapshots)
                {
                    if (!liveCuaUids.Contains(entry.Key))
                    {
                        removedCuaUids.Add(entry.Key);
                    }
                }
                int removedOffset;
                for (removedOffset = 0;
                     removedOffset < removedCuaUids.Count;
                     removedOffset++)
                {
                    _cuaChoiceSnapshots.Remove(
                        removedCuaUids[removedOffset]);
                }
                List<string> removedPersonUids = new List<string>();
                foreach (
                    KeyValuePair<string, PersonClothingSnapshot> entry
                    in _personClothingSnapshots)
                {
                    if (!livePersonUids.Contains(entry.Key))
                    {
                        removedPersonUids.Add(entry.Key);
                    }
                }
                for (removedOffset = 0;
                     removedOffset < removedPersonUids.Count;
                     removedOffset++)
                {
                    _personClothingSnapshots.Remove(
                        removedPersonUids[removedOffset]);
                }
                removedPersonUids.Clear();
                foreach (
                    KeyValuePair<string, PersonHairSnapshot> entry
                    in _personHairSnapshots)
                {
                    if (!livePersonUids.Contains(entry.Key))
                    {
                        removedPersonUids.Add(entry.Key);
                    }
                }
                for (removedOffset = 0;
                     removedOffset < removedPersonUids.Count;
                     removedOffset++)
                {
                    _personHairSnapshots.Remove(
                        removedPersonUids[removedOffset]);
                }
                removedPersonUids.Clear();
                foreach (
                    KeyValuePair<
                        string,
                        PersonBodyProportionSnapshot> entry
                    in _personBodyProportionSnapshots)
                {
                    if (!livePersonUids.Contains(entry.Key))
                    {
                        removedPersonUids.Add(entry.Key);
                    }
                }
                foreach (
                    KeyValuePair<
                        string,
                        PersonBodyProportionUndo> entry
                    in _personBodyProportionUndo)
                {
                    if (!livePersonUids.Contains(entry.Key) &&
                        !removedPersonUids.Contains(entry.Key))
                    {
                        removedPersonUids.Add(entry.Key);
                    }
                }
                foreach (
                    KeyValuePair<
                        string,
                        PersonBodyShapeCache> entry
                    in _personBodyShapeCaches)
                {
                    if (!livePersonUids.Contains(entry.Key) &&
                        !removedPersonUids.Contains(entry.Key))
                    {
                        removedPersonUids.Add(entry.Key);
                    }
                }
                foreach (
                    KeyValuePair<
                        string,
                        PersonBodyShapeBuild> entry
                    in _personBodyShapeBuilds)
                {
                    if (!livePersonUids.Contains(entry.Key) &&
                        !removedPersonUids.Contains(entry.Key))
                    {
                        removedPersonUids.Add(entry.Key);
                    }
                }
                for (removedOffset = 0;
                     removedOffset < removedPersonUids.Count;
                     removedOffset++)
                {
                    string removedUid =
                        removedPersonUids[removedOffset];
                    _personBodyProportionSnapshots.Remove(
                        removedUid);
                    _personBodyProportionUndo.Remove(
                        removedUid);
                    _personBodyShapeCaches.Remove(
                        removedUid);
                    CancelPersonBodyShapeBuild(
                        removedUid);
                }
                scene["atoms"] = atoms;
                scene["persons"] = persons;
                JSONClass sam3d = new JSONClass();
                Sam3dUndoSnapshot liveSam3dSnapshot =
                    loading
                    ? null
                    : CurrentSam3dSnapshot();
                bool sam3dApplied = liveSam3dSnapshot != null;
                sam3d["applied"].AsBool = sam3dApplied;
                sam3d["undoAvailable"].AsBool = sam3dApplied;
                if (sam3dApplied)
                {
                    sam3d["jobId"] =
                        liveSam3dSnapshot.JobId ?? "";
                    sam3d["revision"] =
                        liveSam3dSnapshot.Revision ?? "";
                    sam3d["targetUid"] =
                        liveSam3dSnapshot.TargetUid ?? "";
                    sam3d["cameraUid"] =
                        liveSam3dSnapshot.CameraUid ?? "";
                    JSONClass settlement =
                        BuildSam3dSettlementStatus(
                            liveSam3dSnapshot.Diagnostics);
                    if (settlement != null)
                    {
                        sam3d["settlement"] = settlement;
                    }
                }
                if (_lastSam3dRequestId.Length != 0)
                {
                    JSONClass lastAction = new JSONClass();
                    lastAction["requestId"] =
                        _lastSam3dRequestId;
                    lastAction["command"] =
                        _lastSam3dCommand;
                    lastAction["jobId"] =
                        _lastSam3dJobId;
                    lastAction["revision"] =
                        _lastSam3dRevision;
                    lastAction["cameraUid"] =
                        _lastSam3dCameraUid;
                    lastAction["state"] =
                        _lastSam3dState;
                    lastAction["message"] =
                        _lastSam3dMessage;
                    sam3d["lastAction"] = lastAction;
                }
                sam3d["reference"] =
                    BuildSam3dReferenceStatus();
                scene["sam3d"] = sam3d;
                scene["capabilities"] = Capabilities();
                FileManagerSecure.WriteAllText(ScenePath, scene.ToString());
            }
            catch (Exception exception)
            {
                SuperController.LogError(
                    "[VAM-PIP Bridge] Could not write scene status: " +
                    DescribeException(exception));
            }
        }

        private void PublishStatus(
            string state,
            string requestId,
            string startedAtUtc,
            string finishedAtUtc,
            string backend,
            string message)
        {
            string signature =
                state + "\n" +
                requestId + "\n" +
                startedAtUtc + "\n" +
                finishedAtUtc + "\n" +
                backend + "\n" +
                message + "\n" +
                _lastCompletedRequestId;
            if (signature == _lastPublishedStatusSignature)
            {
                return;
            }

            try
            {
                JSONClass status = new JSONClass();
                status["protocol"].AsInt = ProtocolVersion;
                status["bridgeVersion"] = BridgeVersion;
                status["instanceId"] = _instanceId;
                status["requestId"] = requestId ?? "";
                status["lastCompletedRequestId"] = _lastCompletedRequestId;
                status["state"] = state;
                status["ok"].AsBool = state == StateOk;
                status["updatedAtUtc"] = UtcNow();
                status["startedAtUtc"] = startedAtUtc ?? "";
                status["finishedAtUtc"] = finishedAtUtc ?? "";
                status["backend"] = backend ?? "";
                status["message"] = message ?? "";
                status["capabilities"] = Capabilities();

                FileManagerSecure.WriteAllText(StatusPath, status.ToString());
                _lastPublishedStatusSignature = signature;
            }
            catch (Exception exception)
            {
                SuperController.LogError(
                    "[VAM-PIP Bridge] Could not write status: " +
                    DescribeException(exception));
            }
        }

        private static string DescribeException(Exception exception)
        {
            if (exception == null)
            {
                return "Unknown error.";
            }

            // Runtime type inspection in diagnostics emits a prohibited
            // metadata call on VaM's legacy Mono runtime.
            string message = exception.Message ?? "";
            message = message.Replace("\r", " ").Replace("\n", " ").Trim();
            if (message.Length == 0)
            {
                message = "Unspecified error.";
            }
            if (message.Length > 1000)
            {
                message = message.Substring(0, 1000);
            }
            return message;
        }
    }
}
