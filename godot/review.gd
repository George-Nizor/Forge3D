extends Node3D

const REPORT_SCHEMA_VERSION := 1
const DEFAULT_REPORT_PATH := "user://forge3d-review.json"

var _asset_root: Node3D
var _camera: Camera3D
var _status_label: Label
var _options: Dictionary = {}
var _errors: Array[String] = []
var _warnings: Array[String] = []
var _animation_targets: Array[Dictionary] = []
var _animation_report: Array[Dictionary] = []
var _current_animation := -1
var _bounds := AABB()
var _has_bounds := false
var _stats := {
	"node_count": 0,
	"mesh_instances": 0,
	"surfaces": 0,
	"vertices": 0,
	"triangles": 0,
	"collision_helpers": 0,
	"collision_triangles": 0,
	"material_surfaces": 0,
	"missing_material_surfaces": 0,
	"blend_shapes": 0,
	"skeletons": 0,
	"bones": 0,
	"animation_players": 0,
	"animations": 0,
}
var _asset_path := ""
var _report_path := ""


func _ready() -> void:
	_options = _parse_options(OS.get_cmdline_user_args())
	_create_review_environment()
	_asset_path = _normalize_path(
		str(_options.get("asset", OS.get_environment("FORGE3D_ASSET")))
	)
	_report_path = _normalize_path(
		str(_options.get("report", OS.get_environment("FORGE3D_REPORT")))
	)
	if _report_path.is_empty():
		_report_path = ProjectSettings.globalize_path(DEFAULT_REPORT_PATH)

	if _asset_path.is_empty():
		_errors.append(
			"No asset supplied. Pass --asset=<file.glb> after Godot's `--` separator."
		)
		_finish_review()
		return
	if not FileAccess.file_exists(_asset_path):
		_errors.append("Asset does not exist: %s" % _asset_path)
		_finish_review()
		return
	if _asset_path.get_extension().to_lower() not in ["glb", "gltf"]:
		_errors.append("Review harness accepts .glb or .gltf files: %s" % _asset_path)
		_finish_review()
		return

	var gltf_document := GLTFDocument.new()
	var gltf_state := GLTFState.new()
	var import_error := gltf_document.append_from_file(_asset_path, gltf_state)
	if import_error != OK:
		_errors.append(
			"Godot could not load the glTF (error %d: %s)."
			% [import_error, error_string(import_error)]
		)
		_finish_review()
		return

	var imported_scene := gltf_document.generate_scene(gltf_state)
	if imported_scene == null:
		_errors.append("GLTFDocument generated an empty scene.")
		_finish_review()
		return

	imported_scene.name = "ReviewedAsset"
	_asset_root.add_child(imported_scene)
	await get_tree().process_frame
	_inspect_node(imported_scene)
	_validate_asset()
	_frame_camera()
	_select_initial_animation()
	_finish_review()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_left"):
		_step_animation(-1)
	elif event.is_action_pressed("ui_right"):
		_step_animation(1)
	elif event.is_action_pressed("ui_accept"):
		_toggle_animation()


func _parse_options(arguments: PackedStringArray) -> Dictionary:
	var result := {}
	for argument in arguments:
		if not argument.begins_with("--"):
			continue
		var separator := argument.find("=")
		if separator < 0:
			result[argument.trim_prefix("--")] = true
			continue
		var key := argument.substr(2, separator - 2)
		result[key] = argument.substr(separator + 1)
	return result


func _normalize_path(path: String) -> String:
	var normalized := path.strip_edges()
	if normalized.is_empty():
		return ""
	if normalized.begins_with("res://") or normalized.begins_with("user://"):
		return ProjectSettings.globalize_path(normalized)
	return normalized.replace("\\", "/")


func _create_review_environment() -> void:
	_asset_root = Node3D.new()
	_asset_root.name = "Asset"
	add_child(_asset_root)

	var world_environment := WorldEnvironment.new()
	world_environment.name = "ReviewEnvironment"
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.025, 0.03, 0.045)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.62, 0.68, 0.82)
	environment.ambient_light_energy = 0.75
	environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	world_environment.environment = environment
	add_child(world_environment)

	var key_light := DirectionalLight3D.new()
	key_light.name = "KeyLight"
	key_light.rotation_degrees = Vector3(-48.0, -35.0, 0.0)
	key_light.light_color = Color(1.0, 0.93, 0.84)
	key_light.light_energy = 2.1
	key_light.shadow_enabled = true
	add_child(key_light)

	var fill_light := DirectionalLight3D.new()
	fill_light.name = "FillLight"
	fill_light.rotation_degrees = Vector3(35.0, 145.0, 0.0)
	fill_light.light_color = Color(0.55, 0.7, 1.0)
	fill_light.light_energy = 0.65
	add_child(fill_light)

	_camera = Camera3D.new()
	_camera.name = "ReviewCamera"
	_camera.fov = 38.0
	_camera.current = true
	add_child(_camera)

	var canvas := CanvasLayer.new()
	canvas.name = "ReviewOverlay"
	add_child(canvas)
	_status_label = Label.new()
	_status_label.position = Vector2(16.0, 14.0)
	_status_label.add_theme_color_override("font_color", Color(0.92, 0.95, 1.0))
	_status_label.add_theme_color_override("font_shadow_color", Color(0.0, 0.0, 0.0, 0.9))
	_status_label.add_theme_constant_override("shadow_offset_x", 1)
	_status_label.add_theme_constant_override("shadow_offset_y", 1)
	_status_label.text = "Forge3D Review\nWaiting for asset..."
	canvas.add_child(_status_label)


func _inspect_node(node: Node) -> void:
	_stats["node_count"] = int(_stats["node_count"]) + 1

	if node is MeshInstance3D:
		var mesh_instance := node as MeshInstance3D
		if _is_collision_helper(mesh_instance.name):
			_inspect_collision_mesh(mesh_instance)
		else:
			_inspect_mesh(mesh_instance)
	elif node is Skeleton3D:
		var skeleton := node as Skeleton3D
		_stats["skeletons"] = int(_stats["skeletons"]) + 1
		_stats["bones"] = int(_stats["bones"]) + skeleton.get_bone_count()
	elif node is AnimationPlayer:
		_inspect_animation_player(node as AnimationPlayer)

	for child in node.get_children():
		_inspect_node(child)


func _is_collision_helper(node_name: StringName) -> bool:
	var normalized := str(node_name).to_lower()
	return (
		normalized.ends_with("-col")
		or normalized.ends_with("-colonly")
		or normalized.ends_with("-convcol")
		or normalized.ends_with("-convcolonly")
	)


func _inspect_collision_mesh(mesh_instance: MeshInstance3D) -> void:
	_stats["collision_helpers"] = int(_stats["collision_helpers"]) + 1
	mesh_instance.visible = false
	var mesh := mesh_instance.mesh
	if mesh == null:
		_warnings.append("Collision helper `%s` has no mesh resource." % mesh_instance.name)
		return
	for surface_index in mesh.get_surface_count():
		if mesh.surface_get_primitive_type(surface_index) != Mesh.PRIMITIVE_TRIANGLES:
			continue
		var arrays := mesh.surface_get_arrays(surface_index)
		var vertex_count := 0
		var index_count := 0
		if arrays.size() > Mesh.ARRAY_VERTEX and arrays[Mesh.ARRAY_VERTEX] != null:
			vertex_count = arrays[Mesh.ARRAY_VERTEX].size()
		if arrays.size() > Mesh.ARRAY_INDEX and arrays[Mesh.ARRAY_INDEX] != null:
			index_count = arrays[Mesh.ARRAY_INDEX].size()
		_stats["collision_triangles"] = (
			int(_stats["collision_triangles"])
			+ (index_count / 3 if index_count > 0 else vertex_count / 3)
		)


func _inspect_mesh(mesh_instance: MeshInstance3D) -> void:
	_stats["mesh_instances"] = int(_stats["mesh_instances"]) + 1
	var mesh := mesh_instance.mesh
	if mesh == null:
		_warnings.append("MeshInstance3D `%s` has no mesh resource." % mesh_instance.name)
		return

	var local_bounds := mesh_instance.get_aabb()
	var world_bounds := _transform_aabb(local_bounds, mesh_instance.global_transform)
	if _has_bounds:
		_bounds = _bounds.merge(world_bounds)
	else:
		_bounds = world_bounds
		_has_bounds = true

	_stats["blend_shapes"] = int(_stats["blend_shapes"]) + mesh.get_blend_shape_count()
	for surface_index in mesh.get_surface_count():
		_stats["surfaces"] = int(_stats["surfaces"]) + 1
		var arrays := mesh.surface_get_arrays(surface_index)
		var vertex_count := 0
		var index_count := 0
		if arrays.size() > Mesh.ARRAY_VERTEX and arrays[Mesh.ARRAY_VERTEX] != null:
			vertex_count = arrays[Mesh.ARRAY_VERTEX].size()
		if arrays.size() > Mesh.ARRAY_INDEX and arrays[Mesh.ARRAY_INDEX] != null:
			index_count = arrays[Mesh.ARRAY_INDEX].size()
		_stats["vertices"] = int(_stats["vertices"]) + vertex_count
		if mesh.surface_get_primitive_type(surface_index) == Mesh.PRIMITIVE_TRIANGLES:
			_stats["triangles"] = (
				int(_stats["triangles"]) + (index_count / 3 if index_count > 0 else vertex_count / 3)
			)
		else:
			_warnings.append(
				"Mesh `%s` surface %d is not triangle topology."
				% [mesh_instance.name, surface_index]
			)

		var material := mesh_instance.get_surface_override_material(surface_index)
		if material == null:
			material = mesh.surface_get_material(surface_index)
		if material == null:
			_stats["missing_material_surfaces"] = (
				int(_stats["missing_material_surfaces"]) + 1
			)
		else:
			_stats["material_surfaces"] = int(_stats["material_surfaces"]) + 1


func _inspect_animation_player(player: AnimationPlayer) -> void:
	_stats["animation_players"] = int(_stats["animation_players"]) + 1
	for animation_name in player.get_animation_list():
		var animation := player.get_animation(animation_name)
		if animation == null:
			continue
		var entry := {
			"player": str(player.get_path()),
			"name": str(animation_name),
			"length_seconds": animation.length,
			"loop_mode": int(animation.loop_mode),
			"track_count": animation.get_track_count(),
		}
		_animation_report.append(entry)
		_stats["animations"] = int(_stats["animations"]) + 1
		if str(animation_name) != "RESET":
			_animation_targets.append(
				{
					"player": player,
					"name": StringName(animation_name),
				}
			)


func _transform_aabb(local_bounds: AABB, transform: Transform3D) -> AABB:
	var first_point := transform * local_bounds.position
	var transformed := AABB(first_point, Vector3.ZERO)
	for x_index in 2:
		for y_index in 2:
			for z_index in 2:
				var corner := local_bounds.position + Vector3(
					local_bounds.size.x * x_index,
					local_bounds.size.y * y_index,
					local_bounds.size.z * z_index
				)
				transformed = transformed.expand(transform * corner)
	return transformed


func _validate_asset() -> void:
	_validate_expectations()
	if int(_stats["mesh_instances"]) == 0:
		_errors.append("Imported scene contains no MeshInstance3D nodes.")
	if int(_stats["vertices"]) == 0:
		_warnings.append("No surface vertex arrays were available for inspection.")
	if int(_stats["missing_material_surfaces"]) > 0:
		_warnings.append(
			"%d surface(s) have no assigned material."
			% int(_stats["missing_material_surfaces"])
		)
	if not _has_bounds:
		_errors.append("Could not compute an asset bounding box.")
		return
	if not _vector_is_finite(_bounds.position) or not _vector_is_finite(_bounds.size):
		_errors.append("Asset bounds contain NaN or infinite values.")
		return
	var largest_dimension := maxf(_bounds.size.x, maxf(_bounds.size.y, _bounds.size.z))
	if largest_dimension <= 0.0001:
		_errors.append("Asset bounds are effectively zero-sized.")
	elif largest_dimension < 0.01:
		_warnings.append(
			"Asset is smaller than 1 cm; verify Blender-to-Godot scale."
		)
	elif largest_dimension > 1000.0:
		_warnings.append(
			"Asset is larger than 1 km; verify Blender-to-Godot scale."
		)


func _validate_expectations() -> void:
	if _options.has("expect-animation"):
		var expected_animation := str(_options["expect-animation"]).strip_edges()
		if expected_animation.is_empty():
			_append_error_once("--expect-animation requires a non-empty animation name.")
		elif _find_animation_target_index(expected_animation) < 0:
			_append_error_once(
				"Expected animation `%s` was not found." % expected_animation
			)

	if _options.has("expect-skeletons"):
		var raw_expected_skeletons := str(_options["expect-skeletons"]).strip_edges()
		if not raw_expected_skeletons.is_valid_int():
			_append_error_once(
				"--expect-skeletons must be a non-negative integer, got `%s`."
				% raw_expected_skeletons
			)
			return
		var expected_skeletons := int(raw_expected_skeletons)
		if expected_skeletons < 0:
			_append_error_once(
				"--expect-skeletons must be a non-negative integer, got `%s`."
				% raw_expected_skeletons
			)
			return
		var actual_skeletons := int(_stats["skeletons"])
		if actual_skeletons != expected_skeletons:
			_append_error_once(
				"Expected %d Skeleton3D node(s), found %d."
				% [expected_skeletons, actual_skeletons]
			)


func _vector_is_finite(value: Vector3) -> bool:
	return is_finite(value.x) and is_finite(value.y) and is_finite(value.z)


func _frame_camera() -> void:
	if not _has_bounds:
		_camera.position = Vector3(2.5, 1.8, 2.5)
		_camera.look_at(Vector3.ZERO, Vector3.UP)
		return
	var center := _bounds.get_center()
	var radius := maxf(_bounds.size.length() * 0.5, 0.05)
	var half_fov_radians := deg_to_rad(_camera.fov * 0.5)
	var distance := (radius / tan(half_fov_radians)) * 1.15
	var view_direction := Vector3(1.0, 0.55, 1.0).normalized()
	_camera.global_position = center + view_direction * distance
	_camera.near = maxf(0.001, distance - radius * 2.5)
	_camera.far = maxf(100.0, distance + radius * 8.0)
	_camera.look_at(center, Vector3.UP)


func _select_initial_animation() -> void:
	var requested := str(_options.get("animation", "")).strip_edges()
	var expected := str(_options.get("expect-animation", "")).strip_edges()
	var preferred := requested if not requested.is_empty() else expected
	if not preferred.is_empty():
		var preferred_index := _find_animation_target_index(preferred)
		if preferred_index >= 0:
			_play_animation(preferred_index)
		elif not requested.is_empty():
			_append_error_once(
				"Requested animation `%s` was not found; no fallback animation was selected."
				% requested
			)
		return
	if _options.has("expect-animation"):
		# An explicitly supplied but empty expectation is invalid. Validation
		# reports the error; do not obscure it by playing an arbitrary clip.
		return
	if _animation_targets.is_empty():
		return
	_play_animation(0)


func _find_animation_target_index(animation_name: String) -> int:
	for index in _animation_targets.size():
		if str(_animation_targets[index]["name"]) == animation_name:
			return index
	return -1


func _append_error_once(message: String) -> void:
	if message not in _errors:
		_errors.append(message)


func _step_animation(direction: int) -> void:
	if _animation_targets.is_empty():
		return
	var next_index := posmod(_current_animation + direction, _animation_targets.size())
	_play_animation(next_index)
	_update_overlay()


func _play_animation(index: int) -> void:
	if index < 0 or index >= _animation_targets.size():
		return
	if _current_animation >= 0:
		var old_player := _animation_targets[_current_animation]["player"] as AnimationPlayer
		old_player.stop()
	_current_animation = index
	var target := _animation_targets[index]
	var player := target["player"] as AnimationPlayer
	player.play(target["name"])


func _toggle_animation() -> void:
	if _current_animation < 0:
		return
	var player := _animation_targets[_current_animation]["player"] as AnimationPlayer
	if player.is_playing():
		player.pause()
	else:
		player.play()
	_update_overlay()


func _finish_review() -> void:
	_update_overlay()
	var report := _build_report()
	_write_report(report)
	print("FORGE3D_REVIEW_REPORT=%s" % _report_path)
	print("FORGE3D_REVIEW_JSON=%s" % JSON.stringify(report))

	if bool(_options.get("quit-after-report", false)):
		var exit_code := 2 if not _errors.is_empty() else 0
		get_tree().quit(exit_code)


func _build_report() -> Dictionary:
	var status := "pass"
	if not _errors.is_empty():
		status = "fail"
	elif not _warnings.is_empty():
		status = "warn"
	var selected_animation := ""
	if _current_animation >= 0:
		selected_animation = str(_animation_targets[_current_animation]["name"])
	return {
		"schema_version": REPORT_SCHEMA_VERSION,
		"status": status,
		"asset": _asset_path,
		"report": _report_path,
		"godot_version": Engine.get_version_info(),
		"generated_utc": Time.get_datetime_string_from_system(true),
		"errors": _errors,
		"warnings": _warnings,
		"statistics": _stats,
		"bounds": _aabb_to_dictionary(_bounds) if _has_bounds else null,
		"animations": _animation_report,
		"selected_animation": selected_animation,
		"expectations": _build_expectation_report(),
	}


func _build_expectation_report() -> Dictionary:
	var result := {
		"requested_animation": str(_options.get("animation", "")),
		"expected_animation": null,
		"expected_animation_found": null,
		"expected_skeletons": null,
		"actual_skeletons": int(_stats["skeletons"]),
		"skeleton_count_matches": null,
	}
	if _options.has("expect-animation"):
		var expected_animation := str(_options["expect-animation"]).strip_edges()
		result["expected_animation"] = expected_animation
		result["expected_animation_found"] = (
			not expected_animation.is_empty()
			and _find_animation_target_index(expected_animation) >= 0
		)
	if _options.has("expect-skeletons"):
		var raw_expected_skeletons := str(_options["expect-skeletons"]).strip_edges()
		if raw_expected_skeletons.is_valid_int() and int(raw_expected_skeletons) >= 0:
			var expected_skeletons := int(raw_expected_skeletons)
			result["expected_skeletons"] = expected_skeletons
			result["skeleton_count_matches"] = (
				int(_stats["skeletons"]) == expected_skeletons
			)
	return result


func _aabb_to_dictionary(value: AABB) -> Dictionary:
	return {
		"position": _vector_to_dictionary(value.position),
		"size": _vector_to_dictionary(value.size),
		"center": _vector_to_dictionary(value.get_center()),
	}


func _vector_to_dictionary(value: Vector3) -> Dictionary:
	return {
		"x": value.x,
		"y": value.y,
		"z": value.z,
	}


func _write_report(report: Dictionary) -> void:
	var report_directory := _report_path.get_base_dir()
	var directory_error := DirAccess.make_dir_recursive_absolute(report_directory)
	if directory_error != OK and directory_error != ERR_ALREADY_EXISTS:
		push_error(
			"Could not create report directory `%s`: %s"
			% [report_directory, error_string(directory_error)]
		)
		return
	var file := FileAccess.open(_report_path, FileAccess.WRITE)
	if file == null:
		push_error(
			"Could not write report `%s`: %s"
			% [_report_path, error_string(FileAccess.get_open_error())]
		)
		return
	file.store_string(JSON.stringify(report, "\t"))


func _update_overlay() -> void:
	if _status_label == null:
		return
	var status := "PASS"
	if not _errors.is_empty():
		status = "FAIL"
	elif not _warnings.is_empty():
		status = "WARN"
	var animation_name := "none"
	if _current_animation >= 0:
		animation_name = str(_animation_targets[_current_animation]["name"])
	_status_label.text = (
		"Forge3D Review — %s\n"
		+ "%s\n"
		+ "Meshes: %d  Vertices: %d  Triangles: %d  Bones: %d\n"
		+ "Animation: %s  (Left/Right: change, Enter: pause)\n"
		+ "Warnings: %d  Errors: %d"
	) % [
		status,
		_asset_path.get_file() if not _asset_path.is_empty() else "No asset",
		int(_stats["mesh_instances"]),
		int(_stats["vertices"]),
		int(_stats["triangles"]),
		int(_stats["bones"]),
		animation_name,
		_warnings.size(),
		_errors.size(),
	]
