/* Generated from Python public contracts. Do not edit manually. */

export type CrsTransform = string | null;
export type QualityCheck = string[];
export type Resampling = ('nearest' | 'bilinear' | 'cubic' | 'sum' | 'area_weighted') | null;
export type SemanticMapping = string;
export type Id = string;
export type Version = number;
export type Status = 'VALIDATED' | 'BLOCKED' | 'MANUAL_REVIEW';
export type NodeId = string;
export type Variable = string;
export type TemporalTransform = ('nearest' | 'mean' | 'sum' | 'min' | 'max' | 'interpolation') | null;
export type UnitConversion = string | null;
export type Checksum = string;
export type Crs = string | null;
export type Format =
  'GeoTIFF' | 'COG' | 'GeoJSON' | 'Shapefile' | 'GeoPackage' | 'CSV' | 'NetCDF' | 'JSON' | 'HTTP' | 'DATABASE';
export type Id1 = string;
export type License = string;
export type Name = string;
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
export type Name1 = string;
export type NodataPolicy = 'reject' | 'mask' | 'propagate';
export type Required = boolean;
export type SemanticType = 'continuous' | 'categorical' | 'extensive';
export type SpatialSupport = string;
export type StandardName = string;
export type TemporalSupport = string;
export type Unit = string;
export type Variables = VariableSpec[];
export type Version1 = number;
export type VerticalDatum = string | null;
export type CancelRequested = boolean;
export type CurrentNode = string | null;
export type Error = {
  [k: string]: JsonValue;
} | null;
export type FinishedAt = string | null;
export type Id2 = string;
export type Logs = string[];
export type Progress = number;
export type SceneId = string;
export type StartedAt = string | null;
export type Status1 = 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED';
export type SubmittedBy = string;
export type WorkflowId = string;
export type AssessmentMethod = 'composite' | 'topsis';
export type OriginalText = string;
export type SeaLevelIncrementM = number | null;
export type Template = 'coastal_impact' | 'sustainability' | 'temporal_change';
export type WeightMethod = 'equal' | 'manual' | 'entropy';
export type Capabilities = string[];
export type Description1 = string;
export type Field = string;
export type Operator = 'eq' | 'ne' | 'ge' | 'le' | 'in' | 'required';
export type Constraints = ConstraintSpec[];
export type CreatedAt = string;
export type Description2 = string;
export type DisplayName = string;
export type Enabled = boolean;
export type ExecutionStatus = 'EXECUTABLE' | 'NOT_EXECUTABLE';
export type Id3 = string;
export type Inputs = VariableSpec[];
export type License1 = string;
export type ModelType = 'STATISTICAL' | 'PROCESS' | 'MACHINE_LEARNING' | 'RASTER' | 'GIS' | 'HYBRID' | 'EXTERNAL';
export type Name2 = string;
export type Outputs = VariableSpec[];
export type Owner = string;
export type Default = number | null;
export type Description3 = string;
export type Maximum = number | null;
export type Minimum = number | null;
export type Name3 = string;
export type Required1 = boolean;
export type Unit1 = string;
export type Parameters = ParameterSpec[];
export type References = string[];
export type RuntimeType = 'python' | 'cli' | 'docker' | 'http' | 'raster_gis' | 'ml' | 'metadata';
export type ScientificDomain = string[];
export type Maximum1 = number | null;
export type Minimum1 = number | null;
export type Unit2 = string;
export type SupportedCrs = string[];
export type SupportedGeometry = string[];
export type UpdatedAt = string;
export type ValidationStatus = 'UNVALIDATED' | 'VALIDATED' | 'REJECTED';
export type Version2 = number;
export type Constraints1 = ConstraintSpec[];
export type SourceNode = string;
export type SourceVariable = string;
export type TargetNode = string;
export type TargetVariable = string;
export type Edges = WorkflowEdge[];
export type MaxRetries = number;
export type TimeoutSeconds = number;
export type Id4 = string;
export type InputBindings = BindingPlan[];
export type Name4 = string;
/**
 * @minItems 1
 */
export type Nodes = [WorkflowNode, ...WorkflowNode[]];
export type Id5 = string;
export type Kind = 'data' | 'transform' | 'model' | 'validation' | 'output';
export type ModelId = string;
export type ModelVersion = number;
export type OutputDefinition = BindingTarget[];
export type NodeId1 = string;
export type Parameter = string;
export type Value = number;
export type ParameterBindings = ParameterBinding[];
export type SceneType = string;
export type ValidationRules = string[];
export type Version3 = number;
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
export type Edges1 = WorkflowEdge[];
export type Nodes1 = WorkflowNode[];
/**
 * @maxItems 128
 */
export type Edges2 = WorkflowEdge[];
/**
 * @maxItems 128
 */
export type InputBindings1 = ProposedBinding[];
/**
 * @minItems 1
 * @maxItems 32
 */
export type Nodes2 = [ProposedNode, ...ProposedNode[]];
export type Id6 = string;
export type Name5 = string;
export type Value1 = number;
export type Parameters2 = ProposedParameter[];
/**
 * @minItems 1
 * @maxItems 64
 */
export type OutputDefinition1 = [BindingTarget, ...BindingTarget[]];
export type ManagementGoal1 = string;
export type MissingConditions1 = string[];
export type Rationale1 = string[];
export type RequiredCapabilities1 = string[];
export type RequiredData2 = string[];
export type TaskGraph1 = string[];
export type Checksum1 = string;
export type CreatedAt1 = string;
export type GeographicEntityId = string;
export type GeographicEntityVersion = number;
export type ManagementUnitId = string | null;
export type ResultObjectId = string;
export type EntityBinding = EntityBinding1[];
export type Id7 = string;
export type JobId = string;
export type Provenance = string;
export type QualityStatus = 'RAW' | 'VALIDATED' | 'REVIEWED' | 'PUBLISHED' | 'REJECTED';
export type ResultType = string;
export type Revision = number;
export type StorageUri = string;
export type End = string;
export type Start = string;
export type Unit3 = string;
export type Bindings = BindingPlan[];
export type ContainerImage = string;
export type DataAssets = DataAssetSpec[];
export type Models = ModelSpec[];
export type Parameters3 = ParameterBinding[];
export type RandomSeed = number;
export type Constraints2 = ConstraintSpec[];
export type EntityTypes = string[];
export type Id8 = string;
export type ManagementGoal2 = string;
export type Name6 = string;
export type RequiredOutputs = string[];
export type Version4 = number;
export type SoftwareVersion = string;
export type Timestamp = string;

export interface CoastMASContracts {
  BindingPlan: BindingPlan;
  DataAssetSpec: DataAssetSpec;
  ExecutionJob: ExecutionJob;
  ManagementGoal: ManagementGoal;
  ModelSpec: ModelSpec;
  PlanningArtifact: PlanningArtifact;
  ProviderProposal: ProviderProposal;
  ResultManifest: ResultManifest;
  RunManifest: RunManifest;
  SceneSpec: SceneSpec;
  WorkflowSpec: WorkflowSpec;
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
export interface VersionReference {
  id: Id;
  version: Version;
}
export interface BindingTarget {
  node_id: NodeId;
  variable: Variable;
}
export interface DataAssetSpec {
  checksum: Checksum;
  crs: Crs;
  format: Format;
  id: Id1;
  license: License;
  name: Name;
  quality: Quality;
  source: Source;
  spatial_extent: Extent | null;
  time_end: TimeEnd;
  time_resolution: TimeResolution;
  time_start: TimeStart;
  type: Type;
  uri: Uri;
  variables: Variables;
  version: Version1;
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
  name: Name1;
  nodata_policy: NodataPolicy;
  required: Required;
  semantic_type: SemanticType;
  spatial_support: SpatialSupport;
  standard_name: StandardName;
  temporal_support: TemporalSupport;
  unit: Unit;
}
export interface ExecutionJob {
  cancel_requested?: CancelRequested;
  current_node: CurrentNode;
  error: Error;
  finished_at: FinishedAt;
  id: Id2;
  logs: Logs;
  progress: Progress;
  scene_id: SceneId;
  started_at: StartedAt;
  status: Status1;
  submitted_by: SubmittedBy;
  workflow_id: WorkflowId;
}
export interface ManagementGoal {
  assessment_method?: AssessmentMethod;
  original_text: OriginalText;
  sea_level_increment_m?: SeaLevelIncrementM;
  template: Template;
  weight_method?: WeightMethod;
}
export interface ModelSpec {
  capabilities: Capabilities;
  constraints: Constraints;
  created_at: CreatedAt;
  description: Description2;
  display_name: DisplayName;
  enabled?: Enabled;
  execution_status?: ExecutionStatus;
  id: Id3;
  inputs: Inputs;
  license: License1;
  model_type: ModelType;
  name: Name2;
  outputs: Outputs;
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
  version: Version2;
}
export interface ConstraintSpec {
  description: Description1;
  field: Field;
  operator: Operator;
  value: JsonValue;
}
export interface ParameterSpec {
  default?: Default;
  description?: Description3;
  maximum?: Maximum;
  minimum?: Minimum;
  name: Name3;
  required?: Required1;
  unit: Unit1;
}
export interface RuntimeConfig {
  [k: string]: JsonValue;
}
export interface ScaleSpec {
  maximum?: Maximum1;
  minimum?: Minimum1;
  unit: Unit2;
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
  edges: Edges;
  execution_policy: ExecutionPolicy;
  id: Id4;
  input_bindings: InputBindings;
  name: Name4;
  nodes: Nodes;
  output_definition: OutputDefinition;
  parameter_bindings: ParameterBindings;
  scene_type: SceneType;
  validation_rules: ValidationRules;
  version: Version3;
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
  id: Id5;
  kind?: Kind;
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
  edges: Edges1;
  nodes: Nodes1;
}
export interface ProviderProposal {
  candidate_workflow: ProposedWorkflow | null;
  management_goal: ManagementGoal1;
  missing_conditions: MissingConditions1;
  rationale: Rationale1;
  required_capabilities: RequiredCapabilities1;
  required_data: RequiredData2;
  task_graph: TaskGraph1;
}
export interface ProposedWorkflow {
  edges: Edges2;
  input_bindings: InputBindings1;
  nodes: Nodes2;
  output_definition: OutputDefinition1;
}
export interface ProposedBinding {
  source: VersionReference;
  target: BindingTarget;
}
export interface ProposedNode {
  id: Id6;
  model: VersionReference;
  parameters: Parameters2;
}
export interface ProposedParameter {
  name: Name5;
  value: Value1;
}
export interface ResultManifest {
  checksum: Checksum1;
  created_at: CreatedAt1;
  entity_binding: EntityBinding;
  id: Id7;
  job_id: JobId;
  provenance: Provenance;
  quality_status: QualityStatus;
  result_type: ResultType;
  revision: Revision;
  spatial_extent: Extent | null;
  storage_uri: StorageUri;
  time_range: TimeRange | null;
  unit: Unit3;
}
export interface EntityBinding1 {
  geographic_entity_id: GeographicEntityId;
  geographic_entity_version: GeographicEntityVersion;
  management_unit_id: ManagementUnitId;
  result_object_id: ResultObjectId;
}
export interface TimeRange {
  end: End;
  start: Start;
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
  entity_types: EntityTypes;
  id: Id8;
  management_goal: ManagementGoal2;
  name: Name6;
  quality_requirements: QualityRequirements;
  required_outputs: RequiredOutputs;
  scenario_conditions: ScenarioConditions;
  study_area: StudyArea;
  time_range: TimeRange;
  version: Version4;
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
