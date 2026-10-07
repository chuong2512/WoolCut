namespace Falcon.Game.Wool.GamePlay.Runtime
{
	using System;
	using System.Collections.Generic;
	using Sirenix.OdinInspector;
	using UnityEngine;
	using UnityEngine.Rendering;
	using Random = UnityEngine.Random;

	[ExecuteInEditMode]
	[RequireComponent(typeof(Renderer), typeof(MeshFilter))]
	public class DissolveVisualizer : MonoBehaviour
	{
		// _Progress lúc len còn nguyên — khớp default của UserWooler Shader và mọi .mat. Lớn hơn mốc này là đang tan.
		private const float RestingProgress = -0.01f;

		// Keyword local của UserWooler Shader: chỉ khi bật shader mới sample noise + clip(). Tắt lúc nghỉ để Adreno
		// giữ được early-Z/LRZ cho toàn bộ len trên bàn.
		private const string DissolveKeywordName = "_WOOL_DISSOLVE";

		[SerializeField, Range(0, 1)] private float   _progress;
		[SerializeField, Range(3, 32)] private int _extremePointCount = 8;

		[Tooltip("The extreme points distributed around the dissolve edge perimeter.")]
		private List<Vector3> _extremeWorldSpacePoints = new();

		public List<Vector3> ExtremeWorldSpacePoints => _extremeWorldSpacePoints;

		private Renderer   _renderer;
		private Material   _material;
		private Mesh       _mesh;
		private MeshFilter _meshFilter;
		private Vector3    _bounds;
		private Vector3    _center;
		private Vector3    _cacheDirection;

		// Keyword cache theo shader/material đang điều khiển — chỉ gọi SetKeyword khi trạng thái thật sự đổi.
		private Shader       _keywordShader;
		private LocalKeyword _dissolveKeyword;
		private Material     _keywordMaterial;
		private bool         _keywordOn;

		// Mesh chép sẵn cho DissolveFrontSimple (giữ suốt lúc tan, trả khi về pool / destroy / đổi mesh).
		private DissolveFrontSimple.MeshData _meshData;

		// Lần tính điểm cắt gần nhất — progress, transform, số điểm không đổi thì giữ nguyên kết quả.
		private bool      _cutValid;
		private float     _cutProgress;
		private int       _cutPointCount;
		private Matrix4x4 _cutMatrix;

		// Cache property IDs for performance
		private static readonly int ProgressID = Shader.PropertyToID("_Progress");
		private static readonly int CullModeID = Shader.PropertyToID("_CullMode");

		private void OnValidate() { TryGetMesh(); }

		private void OnDisable() { ReleaseMeshData(); }

		private void OnDestroy() { ReleaseMeshData(); }

		private void TryGetMesh()
		{
			if (_mesh == null)
			{
				_meshFilter = GetComponent<MeshFilter>();
				BindMesh(_meshFilter.sharedMesh);
				ResetProgress();
			}
		}

		public void Init(Transform wool, Mesh mesh, WoolScript woolScript)
		{
			TryGetMesh();
			transform.SetParent(wool.transform, worldPositionStays: false);
			transform.localPosition = Vector3.zero;
			transform.localRotation = Quaternion.identity;
			transform.localScale    = Vector3.one;

			/*var lineObj     = new GameObject("Line");
			int targetLayer = LayerMask.NameToLayer("Water");
			lineObj.layer = targetLayer;*/
			var woolRope = GetComponentInChildren<WoolRopeController>();
			woolRope.SetDissolveScript(this);
			_meshFilter.sharedMesh = mesh;
			// Gắn mesh mới TRƯỚC ResetProgress — bản cũ để _mesh của lượt dùng trước nên reset tính điểm cắt
			// (đọc cả mesh) cho một mesh đã bỏ đi.
			BindMesh(mesh);

			woolScript.SetWoolRope(woolRope);
			ResetProgress();
		}

		public void Setup(Renderer render, MeshFilter meshFilter, Material material)
		{
			_renderer          = render;
			_renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
			_renderer.receiveShadows    = false;
			_material                   = material;
			_renderer.material          = _material;

			_meshFilter = meshFilter;
			BindMesh(meshFilter.sharedMesh);

			_extremeWorldSpacePoints.Clear();
			_cutValid = false;

			ResetProgress();
		}

		private void ResetProgress()
		{
			if (_mesh == null) return;
			_progress = 0f;
			UpdateProgress(RestingProgress);
			if (_material != null) _material.SetInt(CullModeID, 2); // Back faces
		}

		[Button]
		public void UpdateProgress(float progress)
		{
			if (_progress <= 0f && progress > 0f && _material != null)
			{
				_material.SetInt(CullModeID, 0); // Off
			}

			_progress = Mathf.Clamp01(progress);

			if (_material == null) return;
			_material.SetFloat(ProgressID, progress);
			// _Progress và keyword luôn đi cùng nhau: đây là chỗ DUY NHẤT ghi _Progress, mọi material len khác
			// (asset, bản copy) đều ở mốc nghỉ với keyword tắt.
			SetDissolveKeyword(progress > RestingProgress);
			UpdateCutPoints();
		}

		private void SetDissolveKeyword(bool on)
		{
			if (_material == null) return;
			if (_keywordOn == on && ReferenceEquals(_keywordMaterial, _material)) return;

			var shader = _material.shader;
			if (!ReferenceEquals(shader, _keywordShader))
			{
				_keywordShader = shader;
				// FindKeyword không log lỗi khi shader không có keyword (material của mechanic dùng shader khác).
				_dissolveKeyword = shader != null ? shader.keywordSpace.FindKeyword(DissolveKeywordName) : default;
			}

			if (_dissolveKeyword.isValid) _material.SetKeyword(_dissolveKeyword, on);
			_keywordMaterial = _material;
			_keywordOn       = on;
		}

		private void UpdateCutPoints()
		{
			if (_mesh == null)
			{
				_extremeWorldSpacePoints.Clear();
				_cutValid = false;
				return;
			}

			_meshData ??= DissolveFrontSimple.Acquire(_mesh);

			var localToWorld = transform.localToWorldMatrix;
			if (_cutValid && _cutProgress == _progress && _cutPointCount == _extremePointCount && _cutMatrix.Equals(localToWorld))
				return;

			DissolveFrontSimple.SampleCutPoints(_meshData, localToWorld, _progress, _extremePointCount, _extremeWorldSpacePoints);
			_cutValid      = true;
			_cutProgress   = _progress;
			_cutPointCount = _extremePointCount;
			_cutMatrix     = localToWorld;
		}

		private void BindMesh(Mesh mesh)
		{
			if (ReferenceEquals(_mesh, mesh)) return;
			_mesh = mesh;
			ReleaseMeshData();
		}

		private void ReleaseMeshData()
		{
			_cutValid = false;
			if (_meshData == null) return;
			DissolveFrontSimple.Release(_meshData);
			_meshData = null;
		}

#if UNITY_EDITOR
		private void OnDrawGizmosSelected()
		{
			if (Application.isPlaying) return;
			if (_renderer == null)
			{
				_renderer = GetComponent<Renderer>();
				return;
			}

			_renderer = GetComponent<Renderer>();
			_material = _renderer.sharedMaterial;

			var meshFilter = GetComponent<MeshFilter>();
			BindMesh(meshFilter.sharedMesh);

			UpdateProgress(_progress);

			Gizmos.color = Color.yellow;
			float gizmoSize = _renderer.bounds.extents.magnitude * 0.05f;

			var pts = DissolveFrontSimple.SampleCutPoints(_mesh, transform, _progress, _extremePointCount);
			foreach (var point in pts)
			{
				Gizmos.DrawSphere(point, gizmoSize);
			}
		}
#endif
	}
}
