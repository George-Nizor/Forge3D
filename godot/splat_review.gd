extends Node3D

const SPLAT_PATH := "res://assets/splats/game-controller-v001.splat"
const SPLAT_NODE_SCRIPT := preload("res://addons/gdgs/runtime/nodes/gaussian_splat_node.gd")
const COMPOSITOR_EFFECT_SCRIPT := preload("res://addons/gdgs/runtime/compositor/gaussian_compositor_effect.gd")
const TARGET_WIDTH_METRES := 0.188

var asset_pivot: Node3D
var camera: Camera3D
var collision_proxy: MeshInstance3D
var dragging := false
var status_label: Label


func _ready() -> void:
	_build_environment()
	_build_camera_and_floor()
	_build_controller_splat()
	_build_overlay()


func _build_environment() -> void:
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("09111d")
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("9ac7d3")
	environment.ambient_light_energy = 0.18
	var compositor := Compositor.new()
	var gaussian_effect: CompositorEffect = COMPOSITOR_EFFECT_SCRIPT.new()
	gaussian_effect.enabled = true
	compositor.compositor_effects = [gaussian_effect]
	var world_environment := WorldEnvironment.new()
	world_environment.name = "Gaussian_Compositor"
	world_environment.environment = environment
	world_environment.compositor = compositor
	add_child(world_environment)


func _build_camera_and_floor() -> void:
	camera = Camera3D.new()
	camera.name = "Review_Camera"
	camera.position = Vector3(0.0, 0.018, 0.40)
	camera.fov = 42.0
	camera.look_at(Vector3(0.0, 0.0, 0.0), Vector3.UP)
	add_child(camera)

	var light := DirectionalLight3D.new()
	light.name = "Review_Light"
	light.rotation_degrees = Vector3(-48.0, -28.0, 0.0)
	light.light_energy = 1.15
	light.shadow_enabled = true
	add_child(light)

	var floor_mesh := PlaneMesh.new()
	floor_mesh.size = Vector2(1.1, 1.1)
	var floor_material := StandardMaterial3D.new()
	floor_material.albedo_color = Color("111e2b")
	floor_material.metallic = 0.15
	floor_material.roughness = 0.46
	floor_mesh.material = floor_material
	var floor := MeshInstance3D.new()
	floor.name = "Review_Floor"
	floor.mesh = floor_mesh
	floor.position = Vector3(0.0, -0.095, -0.02)
	add_child(floor)


func _build_controller_splat() -> void:
	var gaussian: Resource = load(SPLAT_PATH)
	if gaussian == null:
		push_error("Could not load imported Gaussian resource: %s" % SPLAT_PATH)
		return
	var point_count := int(gaussian.get("point_count"))
	var bounds: AABB = gaussian.get("aabb")
	if point_count <= 0 or bounds.size.x <= 0.0:
		push_error("Imported Gaussian resource has no renderable data")
		return

	asset_pivot = Node3D.new()
	asset_pivot.name = "Controller_Pivot"
	asset_pivot.rotation_degrees = Vector3(0.0, -96.0, 0.0)
	add_child(asset_pivot)

	var splat_node: VisualInstance3D = SPLAT_NODE_SCRIPT.new()
	splat_node.name = "Controller_TripoSplat"
	splat_node.set("gaussian", gaussian)
	# TripoSplat uses the same OpenCV-to-display flip verified by the Spark and
	# KIRI reviews. Setting this before entering the tree also prevents GDGS's
	# generic 180-degree Z fallback from being applied to this known source.
	splat_node.rotation_degrees = Vector3(180.0, 0.0, 0.0)
	var longest_extent := maxf(bounds.size.x, maxf(bounds.size.y, bounds.size.z))
	var scale_factor := TARGET_WIDTH_METRES / longest_extent
	splat_node.scale = Vector3.ONE * scale_factor
	splat_node.position = -bounds.get_center() * scale_factor
	asset_pivot.add_child(splat_node)

	# The splat is visual data, so physics remains a deliberately simple authored
	# proxy. It shares the exact source transform and can be replaced per asset.
	var body := StaticBody3D.new()
	body.name = "Controller_StaticBody"
	var collision := CollisionShape3D.new()
	collision.name = "Controller_BoxCollision"
	var box := BoxShape3D.new()
	box.size = bounds.size
	collision.shape = box
	body.position = bounds.get_center()
	body.add_child(collision)
	splat_node.add_child(body)

	var proxy_box := BoxMesh.new()
	proxy_box.size = bounds.size
	var proxy_material := StandardMaterial3D.new()
	proxy_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	proxy_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	proxy_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	proxy_material.albedo_color = Color(0.08, 0.95, 0.45, 0.10)
	proxy_box.material = proxy_material
	collision_proxy = MeshInstance3D.new()
	collision_proxy.name = "Collision_Proxy_Preview"
	collision_proxy.mesh = proxy_box
	collision_proxy.position = bounds.get_center()
	collision_proxy.visible = false
	splat_node.add_child(collision_proxy)

	var dimensions := bounds.size * scale_factor
	set_meta("forge3d_splat_points", point_count)
	set_meta("forge3d_dimensions_m", dimensions)
	set_meta("forge3d_collision", "BoxShape3D")


func _build_overlay() -> void:
	var panel := PanelContainer.new()
	panel.name = "Review_Overlay"
	panel.position = Vector2(24, 24)
	panel.custom_minimum_size = Vector2(390, 132)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.018, 0.03, 0.052, 0.90)
	style.border_color = Color(0.10, 0.56, 0.63, 0.85)
	style.set_border_width_all(1)
	style.corner_radius_top_left = 10
	style.corner_radius_top_right = 10
	style.corner_radius_bottom_left = 10
	style.corner_radius_bottom_right = 10
	style.content_margin_left = 16
	style.content_margin_right = 16
	style.content_margin_top = 12
	style.content_margin_bottom = 12
	panel.add_theme_stylebox_override("panel", style)
	var text := Label.new()
	text.name = "Status"
	text.add_theme_color_override("font_color", Color("d8f4f4"))
	text.add_theme_font_size_override("font_size", 16)
	var points := int(get_meta("forge3d_splat_points", 0))
	var dimensions: Vector3 = get_meta("forge3d_dimensions_m", Vector3.ZERO)
	text.text = "TRIPOSPLAT → GODOT\n%s Gaussians  •  %s × %s × %s m\nDrag: orbit   Wheel: zoom   C: collision proxy" % [
		str(points), str(snappedf(dimensions.x, 0.001)), str(snappedf(dimensions.y, 0.001)), str(snappedf(dimensions.z, 0.001))
	]
	panel.add_child(text)
	add_child(panel)
	status_label = text


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			dragging = event.pressed
		elif event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_UP:
			camera.position.z = maxf(0.24, camera.position.z - 0.025)
		elif event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			camera.position.z = minf(0.70, camera.position.z + 0.025)
	elif event is InputEventMouseMotion and dragging and asset_pivot != null:
		asset_pivot.rotation_degrees.y -= event.relative.x * 0.28
		asset_pivot.rotation_degrees.x = clampf(asset_pivot.rotation_degrees.x - event.relative.y * 0.22, -70.0, 70.0)
	elif event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_C and collision_proxy != null:
			collision_proxy.visible = not collision_proxy.visible
		elif event.keycode == KEY_SPACE and asset_pivot != null:
			asset_pivot.rotation_degrees = Vector3(0.0, -96.0, 0.0)
			camera.position.z = 0.40
