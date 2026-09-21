/* Generated from Python public contracts. Do not edit manually. */

export type Id = string;
export type Version = number;
export type Id1 = string;
export type Name = string;
export type Version1 = number;
export type CrsTransform = string | null;
export type QualityCheck = string[];
export type Resampling = ('nearest' | 'bilinear' | 'cubic' | 'sum' | 'area_weighted') | null;
export type SemanticMapping = string;
export type Status = 'VALIDATED' | 'BLOCKED' | 'MANUAL_REVIEW';
export type NodeId = string;
export type Variable = string;
export type TemporalTransform = ('nearest' | 'mean' | 'sum' | 'min' | 'max' | 'interpolation') | null;
export type UnitConversion = string | null;
export type Checksum = string;
export type Crs = string | null;
export type Format =
  'GeoTIFF' | 'COG' | 'GeoJSON' | 'Shapefile' | 'GeoPackage' | 'CSV' | 'NetCDF' | 'JSON' | 'HTTP' | 'DATABASE';
export type Id2 = string;
export type License = string;
export type Name1 = string;
export type JsonValue = unknown;
export type Source = string;
export type East = number;
export type North = number;
export type South = number;
export type West = number;
export type TimeEnd = string | null;
export type TimeResolution = string | null;
export type TimeStart = string | null;
export type Type = 'raster' | 'vector' | 'table' | 'json' | 'service' | 'database';
export type Uri = string;
export type AggregationType = 'intensive' | 'extensive' | 'categorical' | 'instantaneous';
export type DataType = 'raster' | 'vector' | 'table' | 'scalar' | 'array' | 'json';
export type Description = string;
export type Dimension = string;
export type Name2 = string;
export type NodataPolicy = 'reject' | 'mask' | 'propagate';
export type Required = boolean;
export type SemanticType = 'continuous' | 'categorical' | 'extensive';
export type SpatialSupport = string;
export type StandardName = string;
export type TemporalSupport = string;
export type Unit = string;
export type Variables = VariableSpec[];
export type Version2 = number;
export type VerticalDatum = string | null;
export type ConnectorId = string;
export type Id3 = string;
export type Kind = 'http' | 'postgresql';
export type Name3 = string;
export type Crs1 = string | null;
export type Format1 = 'GeoTIFF' | 'COG' | 'GeoJSON' | 'Shapefile' | 'GeoPackage' | 'CSV' | 'NetCDF' | 'JSON';
export type License1 = string;
export type Name4 = string;
export type Source1 = string;
export type TimeEnd1 = string | null;
export type TimeResolution1 = string | null;
export type TimeStart1 = string | null;
export type Type1 = 'raster' | 'vector' | 'table' | 'json';
export type Variables1 = VariableSpec[];
export type VerticalDatum1 = string | null;
export type Version3 = number;
/**
 * @maxItems 1000
 */
export type Argv = string[];
export type Atomic = boolean;
export type Description1 = string;
export type Id4 = string;
export type Inputs = string[];
export type Outputs = string[];
export type Signature = string | null;
export type Stage = 'preprocess' | 'compute' | 'postprocess' | 'validate';
/**
 * @maxItems 500
 */
export type Components = ModelComponent[];
/**
 * @maxItems 5000
 */
export type Dependencies = [string, string, ...unknown[]][];
export type Kind1 = 'python' | 'pipeline' | 'cli' | 'declared' | 'black_box';
export type Name5 = string;
export type Source2 = string | null;
export type CancelRequested = boolean;
export type CurrentNode = string | null;
export type Error = {
  [k: string]: JsonValue;
} | null;
export type FinishedAt = string | null;
export type Id5 = string;
export type Logs = string[];
export type Progress = number;
export type SceneId = string;
export type StartedAt = string | null;
export type Status1 = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED';
export type SubmittedBy = string;
export type WorkflowId = string;
export type AssessmentMethod = 'composite' | 'topsis';
export type FrameworkVersion = number;
export type IdempotencyKey = string;
export type Crs2 = string;
export type Geometry =
  PointGeometry | MultiPointGeometry | LineGeometry | MultiLineGeometry | PolygonGeometry | MultiPolygonGeometry;
/**
 * @minItems 2
 * @maxItems 2
 */
export type Coordinates = [number, number, ...unknown[]];
export type Type2 = 'Point';
/**
 * @minItems 1
 */
export type Coordinates1 = [[number, number, ...unknown[]], ...[number, number, ...unknown[]][]];
export type Type3 = 'MultiPoint';
/**
 * @minItems 2
 */
export type Coordinates2 = [
  [number, number, ...unknown[]],
  [number, number, ...unknown[]],
  ...[number, number, ...unknown[]][]
];
export type Type4 = 'LineString';
/**
 * @minItems 1
 */
export type Coordinates3 = [
  [[number, number, ...unknown[]], [number, number, ...unknown[]], ...[number, number, ...unknown[]][]],
  ...[[number, number, ...unknown[]], [number, number, ...unknown[]], ...[number, number, ...unknown[]][]][]
];
export type Type5 = 'MultiLineString';
/**
 * @minItems 1
 */
export type Coordinates4 = [
  [
    [number, number, ...unknown[]],
    [number, number, ...unknown[]],
    [number, number, ...unknown[]],
    [number, number, ...unknown[]],
    ...[number, number, ...unknown[]][]
  ],
  ...[
    [number, number, ...unknown[]],
    [number, number, ...unknown[]],
    [number, number, ...unknown[]],
    [number, number, ...unknown[]],
    ...[number, number, ...unknown[]][]
  ][]
];
export type Type6 = 'Polygon';
/**
 * @minItems 1
 */
export type Coordinates5 = [
  [
    [
      [number, number, ...unknown[]],
      [number, number, ...unknown[]],
      [number, number, ...unknown[]],
      [number, number, ...unknown[]],
      ...[number, number, ...unknown[]][]
    ],
    ...[
      [number, number, ...unknown[]],
      [number, number, ...unknown[]],
      [number, number, ...unknown[]],
      [number, number, ...unknown[]],
      ...[number, number, ...unknown[]][]
    ][]
  ],
  ...[
    [
      [number, number, ...unknown[]],
      [number, number, ...unknown[]],
      [number, number, ...unknown[]],
      [number, number, ...unknown[]],
      ...[number, number, ...unknown[]][]
    ],
    ...[
      [number, number, ...unknown[]],
      [number, number, ...unknown[]],
      [number, number, ...unknown[]],
      [number, number, ...unknown[]],
      ...[number, number, ...unknown[]][]
    ][]
  ][]
];
export type Type7 = 'MultiPolygon';
export type Id6 = string;
export type ManagementUnitId = string | null;
export type Name6 = string;
export type Type8 =
  | 'coast_segment'
  | 'wetland'
  | 'land_parcel'
  | 'administrative_unit'
  | 'management_unit'
  | 'water_body'
  | 'protection_zone'
  | 'custom';
export type ValidFrom = string;
export type ValidTo = string | null;
export type Version4 = number;
export type Evidence = 'declaration' | 'workflow_declaration' | 'contract_candidate' | 'contract_conflict';
export type Id7 = string;
export type Source3 = string;
export type Target = string;
export type Type9 =
  | 'REQUIRES'
  | 'PRODUCES'
  | 'SUPPORTS'
  | 'DEPENDS_ON'
  | 'MAPS_TO'
  | 'VALID_FOR'
  | 'INCOMPATIBLE_WITH'
  | 'DERIVED_FROM'
  | 'CAN_FOLLOW';
/**
 * @maxItems 50000
 */
export type Edges = GraphEdge[];
export type Id8 = string;
export type Label = string;
export type Type10 =
  | 'Objective'
  | 'Task'
  | 'Model'
  | 'Variable'
  | 'DataType'
  | 'EntityType'
  | 'SceneType'
  | 'Constraint'
  | 'DataAsset'
  | 'Scene'
  | 'Workflow';
/**
 * @maxItems 10000
 */
export type Nodes = GraphNode[];
export type ClassBreaks = number[];
export type Demo = boolean;
export type Description2 = string;
export type Id9 = string;
/**
 * @minItems 1
 * @maxItems 100
 */
export type Indicators = [IndicatorDefinition, ...IndicatorDefinition[]];
export type Category = string;
export type Direction = 'positive' | 'negative';
export type Formula = string;
export type IndicatorId = string;
export type Name7 = string;
export type Lower = number;
export type Method = 'fixed_minmax';
export type Upper = number;
export type Unit1 = string;
export type Weight = number | null;
export type WeightMethod = 'equal' | 'manual' | 'entropy';
export type Name8 = string;
export type SpatialSupport1 = 'management_unit' | 'administrative_unit' | 'custom_polygon' | 'grid';
export type Version5 = number;
export type AssessmentMethod1 = 'composite' | 'topsis';
export type OriginalText = string;
export type SeaLevelIncrementM = number | null;
export type Template = 'coastal_impact' | 'sustainability' | 'temporal_change';
export type WeightMethod1 = 'equal' | 'manual' | 'entropy';
export type Components1 = ModelComponent[];
export type Dependencies1 = [string, string, ...unknown[]][];
export type Executable = false;
export type Mode = 'WHITE_BOX' | 'BLACK_BOX';
export type ModelName = string;
export type ReviewRequired = true;
export type Warnings = string[];
export type Capabilities = string[];
export type Description3 = string;
export type Field = string;
export type Operator = 'eq' | 'ne' | 'ge' | 'le' | 'in' | 'required';
export type Constraints = ConstraintSpec[];
export type CreatedAt = string;
export type Description4 = string;
export type DisplayName = string;
export type Enabled = boolean;
export type ExecutionStatus = 'EXECUTABLE' | 'NOT_EXECUTABLE';
export type Id10 = string;
export type Inputs1 = VariableSpec[];
export type License2 = string;
export type ModelType = 'STATISTICAL' | 'PROCESS' | 'MACHINE_LEARNING' | 'RASTER' | 'GIS' | 'HYBRID' | 'EXTERNAL';
export type Name9 = string;
export type Outputs1 = VariableSpec[];
export type Owner = string;
export type Default = number | null;
export type Description5 = string;
export type Maximum = number | null;
export type Minimum = number | null;
export type Name10 = string;
export type Required1 = boolean;
export type Unit2 = string;
export type Parameters = ParameterSpec[];
export type References = string[];
export type RuntimeType = 'python' | 'cli' | 'docker' | 'http' | 'raster_gis' | 'ml' | 'metadata';
export type ScientificDomain = string[];
export type Maximum1 = number | null;
export type Minimum1 = number | null;
export type Unit3 = string;
export type SupportedCrs = string[];
export type SupportedGeometry = string[];
export type UpdatedAt = string;
export type ValidationStatus = 'UNVALIDATED' | 'VALIDATED' | 'REJECTED';
export type Version6 = number;
export type Constraints1 = ConstraintSpec[];
export type SourceNode = string;
export type SourceVariable = string;
export type TargetNode = string;
export type TargetVariable = string;
export type Edges1 = WorkflowEdge[];
export type MaxRetries = number;
export type TimeoutSeconds = number;
export type Id11 = string;
export type InputBindings = BindingPlan[];
export type Name11 = string;
/**
 * @minItems 1
 */
export type Nodes1 = [WorkflowNode, ...WorkflowNode[]];
export type Id12 = string;
export type Kind2 = 'data' | 'transform' | 'model' | 'validation' | 'output';
export type ModelId = string;
export type ModelVersion = number;
export type OutputDefinition = BindingTarget[];
export type NodeId1 = string;
export type Parameter = string;
export type Value = number;
export type ParameterBindings = ParameterBinding[];
export type SceneType = string;
export type ValidationRules = string[];
export type Version7 = number;
export type Code = string;
export type Message = string;
export type NodeId2 = string | null;
export type Variable1 = string | null;
export type MissingConditions = MissingCondition[];
export type ProviderRequests = 0;
export type Rationale = string[];
export type RequiredCapabilities = string[];
export type StandardName1 = string;
export type RequiredData = RequiredData1[];
export type Edges2 = WorkflowEdge[];
export type Nodes2 = WorkflowNode[];
export type ExpectedVersion = number;
export type IdempotencyKey1 = string;
export type InterpretationRequiresReview = true;
export type MissingConditions1 = string[];
export type Origin = 'provider_candidate';
/**
 * @maxItems 128
 */
export type Edges3 = WorkflowEdge[];
/**
 * @maxItems 128
 */
export type InputBindings1 = ProposedBinding[];
/**
 * @minItems 1
 * @maxItems 32
 */
export type Nodes3 = [ProposedNode, ...ProposedNode[]];
export type Id13 = string;
export type Name12 = string;
export type Value1 = number;
export type Parameters2 = ProposedParameter[];
/**
 * @minItems 1
 * @maxItems 64
 */
export type OutputDefinition1 = [BindingTarget, ...BindingTarget[]];
export type ManagementGoal1 = string;
export type MissingConditions2 = string[];
export type Rationale1 = string[];
export type RequiredCapabilities1 = string[];
export type RequiredData2 = string[];
export type TaskGraph1 = string[];
export type RequestId = string;
export type Usage = {
  [k: string]: JsonValue;
} | null;
export type Checksum1 = string;
export type CreatedAt1 = string;
export type GeographicEntityId = string;
export type GeographicEntityVersion = number;
export type ManagementUnitId1 = string | null;
export type ResultObjectId = string;
export type EntityBinding = EntityBinding1[];
export type Id14 = string;
export type JobId = string;
export type Provenance = string;
export type QualityStatus = 'RAW' | 'VALIDATED' | 'REVIEWED' | 'PUBLISHED' | 'REJECTED';
export type ResultType = string;
export type Revision = number;
export type StorageUri = string;
export type End = string;
export type Start = string;
export type Unit4 = string;
export type BindingStatus = 'BOUND' | 'PARTIAL' | 'UNBOUND' | 'NOT_APPLICABLE';
export type EntityBinding2 = EntityBinding1[];
export type Id15 = string;
export type ManagementUnitId2 = string | null;
export type NodeId3 = string;
export type SourcePointer = string;
export type StandardName2 = string;
export type Variable2 = string;
export type Objects = ResultObject[];
export type UnboundObjects = string[];
export type Bindings = BindingPlan[];
export type ContainerImage = string;
export type DataAssets = DataAssetSpec[];
export type Models = ModelSpec[];
export type Parameters3 = ParameterBinding[];
export type RandomSeed = number;
export type Constraints2 = ConstraintSpec[];
/**
 * @maxItems 500
 */
export type DataReferences = VersionReference[];
/**
 * @maxItems 500
 */
export type EntityReferences = VersionReference[];
export type EntityTypes = string[];
export type Id16 = string;
export type ManagementGoal2 = string;
export type Name13 = string;
export type RequiredOutputs = string[];
export type Version8 = number;
export type SoftwareVersion = string;
export type Timestamp = string;
export type FootprintWgs84 = {
  [k: string]: JsonValue;
} | null;
export type Method1 = string;
export type Name14 = string;
export type SpatialFraction = number | null;
export type Status2 = 'COVERED' | 'PARTIAL' | 'OUTSIDE' | 'UNKNOWN';
export type TemporalCoverage = boolean | null;
export type DataCoverage = SceneCoverage[];
export type EntityCoverage = SceneCoverage[];
export type Issues = string[];
export type Valid = boolean;
export type ExpectedVersion1 = number;
export type IdempotencyKey2 = string;

export interface CoastMASContracts {
  AssessmentSpec: AssessmentSpec;
  BindingPlan: BindingPlan;
  DataAssetSpec: DataAssetSpec;
  DataInspection: DataInspection;
  DataSourceSpec: DataSourceSpec;
  DecompositionRequest: DecompositionRequest;
  ExecutionJob: ExecutionJob;
  FrameworkPlanRequest: FrameworkPlanRequest;
  GeographicEntity: GeographicEntity;
  GraphSnapshot: GraphSnapshot;
  IndicatorFrameworkSpec: IndicatorFrameworkSpec;
  ManagementGoal: ManagementGoal;
  ModelDecomposition: ModelDecomposition;
  ModelSpec: ModelSpec;
  PlanningArtifact: PlanningArtifact;
  PrepareIndicatorsRequest: PrepareIndicatorsRequest;
  ProviderPlanningArtifact: ProviderPlanningArtifact;
  ProviderProposal: ProviderProposal;
  ResultManifest: ResultManifest;
  ResultView: ResultView;
  RunManifest: RunManifest;
  SceneInspection: SceneInspection;
  SceneSpec: SceneSpec;
  SourceSnapshotRequest: SourceSnapshotRequest;
  WorkflowSpec: WorkflowSpec;
}
/**
 * A frozen evaluation configuration; run results are read from actual job manifests.
 */
export interface AssessmentSpec {
  data: VersionReference;
  framework: VersionReference;
  id: Id1;
  name: Name;
  scene: VersionReference;
  version: Version1;
  workflow: VersionReference;
}
export interface VersionReference {
  id: Id;
  version: Version;
}
export interface BindingPlan {
  crs_transform: CrsTransform;
  quality_check: QualityCheck;
  resampling: Resampling;
  semantic_mapping: SemanticMapping;
  source: VersionReference;
  status: Status;
  target: BindingTarget;
  temporal_transform: TemporalTransform;
  unit_conversion: UnitConversion;
}
export interface BindingTarget {
  node_id: NodeId;
  variable: Variable;
}
export interface DataAssetSpec {
  checksum: Checksum;
  crs: Crs;
  format: Format;
  id: Id2;
  license: License;
  name: Name1;
  quality: Quality;
  source: Source;
  spatial_extent: Extent | null;
  time_end: TimeEnd;
  time_resolution: TimeResolution;
  time_start: TimeStart;
  type: Type;
  uri: Uri;
  variables: Variables;
  version: Version2;
  vertical_datum: VerticalDatum;
}
export interface Quality {
  [k: string]: JsonValue;
}
export interface Extent {
  east: East;
  north: North;
  south: South;
  west: West;
}
export interface VariableSpec {
  aggregation_type: AggregationType;
  data_type: DataType;
  description: Description;
  dimension: Dimension;
  name: Name2;
  nodata_policy: NodataPolicy;
  required: Required;
  semantic_type: SemanticType;
  spatial_support: SpatialSupport;
  standard_name: StandardName;
  temporal_support: TemporalSupport;
  unit: Unit;
}
export interface DataInspection {
  metadata: Metadata;
  preview: Preview;
}
export interface Metadata {
  [k: string]: JsonValue;
}
export interface Preview {
  [k: string]: JsonValue;
}
export interface DataSourceSpec {
  connector_id: ConnectorId;
  id: Id3;
  kind: Kind;
  name: Name3;
  output: DataAssetMetadata;
  version: Version3;
}
export interface DataAssetMetadata {
  crs?: Crs1;
  format: Format1;
  license: License1;
  name: Name4;
  source: Source1;
  spatial_extent?: Extent | null;
  time_end?: TimeEnd1;
  time_resolution?: TimeResolution1;
  time_start?: TimeStart1;
  type: Type1;
  variables: Variables1;
  vertical_datum?: VerticalDatum1;
}
export interface DecompositionRequest {
  argv?: Argv;
  components?: Components;
  dependencies?: Dependencies;
  kind: Kind1;
  name: Name5;
  source?: Source2;
}
export interface ModelComponent {
  atomic?: Atomic;
  description?: Description1;
  id: Id4;
  inputs?: Inputs;
  outputs?: Outputs;
  signature?: Signature;
  stage: Stage;
}
export interface ExecutionJob {
  cancel_requested?: CancelRequested;
  current_node: CurrentNode;
  error: Error;
  finished_at: FinishedAt;
  id: Id5;
  logs: Logs;
  progress: Progress;
  scene_id: SceneId;
  started_at: StartedAt;
  status: Status1;
  submitted_by: SubmittedBy;
  workflow_id: WorkflowId;
}
export interface FrameworkPlanRequest {
  assessment_method?: AssessmentMethod;
  data: VersionReference;
  framework_version: FrameworkVersion;
  idempotency_key: IdempotencyKey;
  scene: VersionReference;
}
export interface GeographicEntity {
  crs: Crs2;
  geometry: Geometry;
  id: Id6;
  management_unit_id?: ManagementUnitId;
  name: Name6;
  properties?: Properties;
  type: Type8;
  valid_from: ValidFrom;
  valid_to: ValidTo;
  version: Version4;
}
export interface PointGeometry {
  coordinates: Coordinates;
  type: Type2;
}
export interface MultiPointGeometry {
  coordinates: Coordinates1;
  type: Type3;
}
export interface LineGeometry {
  coordinates: Coordinates2;
  type: Type4;
}
export interface MultiLineGeometry {
  coordinates: Coordinates3;
  type: Type5;
}
export interface PolygonGeometry {
  coordinates: Coordinates4;
  type: Type6;
}
export interface MultiPolygonGeometry {
  coordinates: Coordinates5;
  type: Type7;
}
export interface Properties {
  [k: string]: JsonValue;
}
export interface GraphSnapshot {
  edges: Edges;
  nodes: Nodes;
}
export interface GraphEdge {
  evidence: Evidence;
  id: Id7;
  properties?: Properties1;
  source: Source3;
  target: Target;
  type: Type9;
}
export interface Properties1 {
  [k: string]: JsonValue;
}
export interface GraphNode {
  id: Id8;
  label: Label;
  properties?: Properties2;
  resource?: VersionReference | null;
  type: Type10;
}
export interface Properties2 {
  [k: string]: JsonValue;
}
export interface IndicatorFrameworkSpec {
  class_breaks?: ClassBreaks;
  demo?: Demo;
  description: Description2;
  id: Id9;
  indicators: Indicators;
  name: Name8;
  spatial_support: SpatialSupport1;
  version: Version5;
}
export interface IndicatorDefinition {
  category: Category;
  direction: Direction;
  formula: Formula;
  indicator_id: IndicatorId;
  name: Name7;
  normalization: FixedNormalization;
  source: Source4;
  unit: Unit1;
  weight?: Weight;
  weight_method: WeightMethod;
}
export interface FixedNormalization {
  lower: Lower;
  method?: Method;
  upper: Upper;
}
export interface Source4 {
  /**
   * This interface was referenced by `Source4`'s JSON-Schema definition
   * via the `patternProperty` "^[A-Za-z][A-Za-z0-9_]{0,63}$".
   */
  [k: string]: string;
}
export interface ManagementGoal {
  assessment_method?: AssessmentMethod1;
  original_text: OriginalText;
  sea_level_increment_m?: SeaLevelIncrementM;
  template: Template;
  weight_method?: WeightMethod1;
}
export interface ModelDecomposition {
  cli_arguments?: CliArguments;
  components: Components1;
  dependencies: Dependencies1;
  executable?: Executable;
  mode: Mode;
  model_name: ModelName;
  review_required?: ReviewRequired;
  warnings?: Warnings;
}
export interface CliArguments {
  [k: string]: string | boolean;
}
export interface ModelSpec {
  capabilities: Capabilities;
  constraints: Constraints;
  created_at: CreatedAt;
  description: Description4;
  display_name: DisplayName;
  enabled?: Enabled;
  execution_status?: ExecutionStatus;
  id: Id10;
  inputs: Inputs1;
  license: License2;
  model_type: ModelType;
  name: Name9;
  outputs: Outputs1;
  owner: Owner;
  parameters: Parameters;
  references: References;
  runtime_config: RuntimeConfig;
  runtime_type: RuntimeType;
  scientific_domain: ScientificDomain;
  spatial_scale: ScaleSpec;
  supported_crs: SupportedCrs;
  supported_geometry: SupportedGeometry;
  temporal_scale: ScaleSpec;
  updated_at: UpdatedAt;
  validation_metrics: ValidationMetrics;
  validation_status: ValidationStatus;
  version: Version6;
}
export interface ConstraintSpec {
  description: Description3;
  field: Field;
  operator: Operator;
  value: JsonValue;
}
export interface ParameterSpec {
  default?: Default;
  description?: Description5;
  maximum?: Maximum;
  minimum?: Minimum;
  name: Name10;
  required?: Required1;
  unit: Unit2;
}
export interface RuntimeConfig {
  [k: string]: JsonValue;
}
export interface ScaleSpec {
  maximum?: Maximum1;
  minimum?: Minimum1;
  unit: Unit3;
}
export interface ValidationMetrics {
  [k: string]: number;
}
export interface PlanningArtifact {
  candidate_workflow: WorkflowSpec | null;
  management_goal: ManagementGoal;
  missing_conditions: MissingConditions;
  provider_requests?: ProviderRequests;
  rationale: Rationale;
  required_capabilities: RequiredCapabilities;
  required_data: RequiredData;
  scene: VersionReference;
  task_graph: TaskGraph;
}
export interface WorkflowSpec {
  constraints: Constraints1;
  edges: Edges1;
  execution_policy: ExecutionPolicy;
  id: Id11;
  input_bindings: InputBindings;
  name: Name11;
  nodes: Nodes1;
  output_definition: OutputDefinition;
  parameter_bindings: ParameterBindings;
  scene_type: SceneType;
  validation_rules: ValidationRules;
  version: Version7;
}
export interface WorkflowEdge {
  source_node: SourceNode;
  source_variable: SourceVariable;
  target_node: TargetNode;
  target_variable: TargetVariable;
}
export interface ExecutionPolicy {
  max_retries: MaxRetries;
  timeout_seconds: TimeoutSeconds;
}
export interface WorkflowNode {
  id: Id12;
  kind?: Kind2;
  model_id: ModelId;
  model_version: ModelVersion;
  parameters?: Parameters1;
}
export interface Parameters1 {
  [k: string]: number;
}
export interface ParameterBinding {
  node_id: NodeId1;
  parameter: Parameter;
  value: Value;
}
export interface MissingCondition {
  code: Code;
  message: Message;
  node_id?: NodeId2;
  variable?: Variable1;
}
export interface RequiredData1 {
  selected: VersionReference | null;
  standard_name: StandardName1;
  target: BindingTarget;
}
export interface TaskGraph {
  edges: Edges2;
  nodes: Nodes2;
}
export interface PrepareIndicatorsRequest {
  data: VersionReference;
  expected_version: ExpectedVersion;
  idempotency_key: IdempotencyKey1;
}
export interface ProviderPlanningArtifact {
  candidate_workflow: WorkflowSpec | null;
  interpretation_requires_review?: InterpretationRequiresReview;
  missing_conditions: MissingConditions1;
  origin?: Origin;
  proposal: ProviderProposal;
  request_id: RequestId;
  usage: Usage;
}
export interface ProviderProposal {
  candidate_workflow: ProposedWorkflow | null;
  management_goal: ManagementGoal1;
  missing_conditions: MissingConditions2;
  rationale: Rationale1;
  required_capabilities: RequiredCapabilities1;
  required_data: RequiredData2;
  task_graph: TaskGraph1;
}
export interface ProposedWorkflow {
  edges: Edges3;
  input_bindings: InputBindings1;
  nodes: Nodes3;
  output_definition: OutputDefinition1;
}
export interface ProposedBinding {
  source: VersionReference;
  target: BindingTarget;
}
export interface ProposedNode {
  id: Id13;
  model: VersionReference;
  parameters: Parameters2;
}
export interface ProposedParameter {
  name: Name12;
  value: Value1;
}
export interface ResultManifest {
  checksum: Checksum1;
  created_at: CreatedAt1;
  entity_binding: EntityBinding;
  id: Id14;
  job_id: JobId;
  provenance: Provenance;
  quality_status: QualityStatus;
  result_type: ResultType;
  revision: Revision;
  spatial_extent: Extent | null;
  storage_uri: StorageUri;
  time_range: TimeRange | null;
  unit: Unit4;
}
export interface EntityBinding1 {
  geographic_entity_id: GeographicEntityId;
  geographic_entity_version: GeographicEntityVersion;
  management_unit_id: ManagementUnitId1;
  result_object_id: ResultObjectId;
}
export interface TimeRange {
  end: End;
  start: Start;
}
export interface ResultView {
  binding_status: BindingStatus;
  entity_binding: EntityBinding2;
  objects: Objects;
  unbound_objects: UnboundObjects;
}
export interface ResultObject {
  id: Id15;
  management_unit_id: ManagementUnitId2;
  model: VersionReference;
  node_id: NodeId3;
  source_pointer: SourcePointer;
  standard_name: StandardName2;
  units?: Units;
  values?: Values;
  variable: Variable2;
}
export interface Units {
  [k: string]: string;
}
export interface Values {
  [k: string]: JsonValue;
}
export interface RunManifest {
  bindings: Bindings;
  container_image: ContainerImage;
  data_assets: DataAssets;
  environment: Environment;
  models: Models;
  parameters: Parameters3;
  random_seed: RandomSeed;
  scene: SceneSpec;
  software_version: SoftwareVersion;
  timestamp: Timestamp;
  workflow: WorkflowSpec;
}
export interface Environment {
  [k: string]: string;
}
export interface SceneSpec {
  constraints: Constraints2;
  data_policy: DataPolicy;
  data_references?: DataReferences;
  entity_references?: EntityReferences;
  entity_types: EntityTypes;
  id: Id16;
  management_goal: ManagementGoal2;
  name: Name13;
  quality_requirements: QualityRequirements;
  required_outputs: RequiredOutputs;
  scenario_conditions: ScenarioConditions;
  study_area: StudyArea;
  time_range: TimeRange;
  version: Version8;
}
export interface DataPolicy {
  [k: string]: JsonValue;
}
export interface QualityRequirements {
  [k: string]: JsonValue;
}
export interface ScenarioConditions {
  [k: string]: JsonValue;
}
export interface StudyArea {
  [k: string]: JsonValue;
}
export interface SceneInspection {
  data_coverage: DataCoverage;
  entity_coverage: EntityCoverage;
  issues: Issues;
  study_area_wgs84: StudyAreaWgs84;
  valid: Valid;
}
export interface SceneCoverage {
  footprint_wgs84?: FootprintWgs84;
  method: Method1;
  name: Name14;
  reference: VersionReference;
  spatial_fraction: SpatialFraction;
  status: Status2;
  temporal_coverage: TemporalCoverage;
}
export interface StudyAreaWgs84 {
  [k: string]: JsonValue;
}
export interface SourceSnapshotRequest {
  expected_version: ExpectedVersion1;
  idempotency_key: IdempotencyKey2;
}
