import glob
from pathlib import Path
import subprocess as sub
import sys
from typing import Dict

import graphviz
import networkx as nx
import yaml

from . import auto_gen_header
from . import ast
from . import cli
from . import compiler
from . import inference
from . import labshare
from . import utils
from .schemas import wic_schema
from .wic_types import Cwl, Yaml, Tool, Tools, YamlTree, GraphReps, GraphData

# Use white for dark backgrounds, black for light backgrounds
font_edge_color = 'white'


def get_tools_cwl(cwl_dir: Path) -> Tools:
    """Uses glob() to find all of the CWL CommandLineTool definition files within any subdirectory of cwl_dir

    Args:
        cwl_dir (Path): The subdirectory in which to search for CWL CommandLineTools

    Returns:
        Tools: The CWL CommandLineTool definitions found using glob()
    """
    # Load ALL of the tools.
    tools_cwl: Tools = {}
    pattern_cwl = str(cwl_dir / '**/*.cwl')
    #print(pattern_cwl)
    # Note that there is a current and a legacy copy of each cwl file for each tool.
    # The only difference appears to be that some legacy parameters are named 
    # *_file as opposed to *_path. Since glob does NOT return the results in
    # any particular order, and since we are using stem as our dict key, current
    # files may be overwritten with legacy files (and vice versa), resulting in
    # an inconsistent naming scheme. Since legacy files are stored in an additional
    # subdirctory, if we sort the paths by descending length, we can overwrite
    # the dict entries of the legacy files.
    cwl_paths_sorted = sorted(glob.glob(pattern_cwl, recursive=True), key=len, reverse=True)
    Path('autogenerated/schemas/tools/').mkdir(parents=True, exist_ok=True)
    for cwl_path_str in cwl_paths_sorted:
        #print(cwl_path)
        try:
            with open(cwl_path_str, 'r') as f:
              tool: Cwl = yaml.safe_load(f.read())
            stem = Path(cwl_path_str).stem
            #print(stem)
            # Add / overwrite stdout and stderr
            tool.update({'stdout': f'{stem}.out'})
            tool.update({'stderr': f'{stem}.err'})
            tools_cwl[stem] = Tool(cwl_path_str, tool)
            #print(tool)
        except yaml.scanner.ScannerError as se:
            pass
            # There are two cwl files that throw this error, but they are both legacy, so...
            #print(cwl_path)
            #print(se)
        #utils.make_tool_DAG(stem, (cwl_path_str, tool))

    return tools_cwl


def get_yml_paths(yml_dir: Path) -> Dict[str, Path]:
    """Uses glob() to find all of the yml workflow definition files within any subdirectory of yml_dir
    NOTE: This function assumes all \*.yml files found are workflow definition files,
    so do not mix regular \*.yml files and workflow files in the same root directory.

    Args:
        yml_dir (Path): The subdirectory in which to search for yml files

    Returns:
        Dict[str, Path]: A dict containing the filepath stem and filepath of each \*.yml file
    """
    # Glob all of the yml files too, so we don't have to deal with relative paths.
    pattern_yml = str(yml_dir / '**/*.yml')
    yml_paths_sorted = sorted(glob.glob(pattern_yml, recursive=True), key=len, reverse=True)
    yml_paths = {}
    for yml_path_str in yml_paths_sorted:
        if '_inputs' not in yml_path_str:
            yml_path = Path(yml_path_str)
            yml_paths[yml_path.stem] = yml_path

    return yml_paths


def main() -> None:
    args = cli.parser.parse_args()

    tools_cwl = get_tools_cwl(Path(args.cwl_dir))
    utils.make_plugins_DAG(tools_cwl)
    yml_paths = get_yml_paths(Path(args.yml_dir))

    # Perform initialization (This is not ideal)
    compiler.inference_rules = dict(utils.read_lines_pairs(Path('inference_rules.txt')))
    inference.renaming_conventions = utils.read_lines_pairs(Path('renaming_conventions.txt'))

    # Generate schemas for validation and vscode IntelliSense code completion
    validator = wic_schema.get_validator(tools_cwl, list(yml_paths), write_to_disk=True)
    if args.generate_schemas_only:
        print('Finished generating schemas. Exiting.')
        sys.exit(0)

    yaml_path = args.yaml
    # Inline ALL subworkflows.
    if args.cwl_inline_subworkflows:
        steps_inlined = utils.inline_sub_steps(yaml_path, tools_cwl, yml_paths)
        with open(Path(yaml_path), 'r') as y:
            yaml_content_in: Yaml = yaml.safe_load(y.read())
        yaml_content_in['steps'] = steps_inlined
        yaml_content_out = yaml.dump(yaml_content_in, sort_keys=False, line_break='\n', indent=2)
        yaml_path = Path(args.yaml).stem + '_inline.yml'
        with open(yaml_path, 'w') as y:
            y.write(auto_gen_header)
            y.write(yaml_content_out)

    # Load the high-level yaml root workflow file.
    with open(yaml_path, 'r') as y:
        root_yaml_tree: Yaml = yaml.safe_load(y.read())
    Path('autogenerated/').mkdir(parents=True, exist_ok=True)
    yaml_tree_raw = ast.read_AST_from_disk(YamlTree(yaml_path, root_yaml_tree), yml_paths, tools_cwl, validator)
    # Write the combined workflow (with all subworkflows as children) to disk.
    with open(f'autogenerated/{Path(yaml_path).stem}_tree_raw.yml', 'w') as f:
        f.write(yaml.dump(yaml_tree_raw.yml))
    yaml_tree = ast.merge_yml_trees(yaml_tree_raw, {}, tools_cwl)
    with open(f'autogenerated/{Path(yaml_path).stem}_tree_merged.yml', 'w') as f:
        f.write(yaml.dump(yaml_tree.yml))

    # TODO: Test new inlineing code
    #namespaces_list = ast.get_inlineable_subworkflows(yaml_tree, tools_cwl, [])
    #for namespaces in namespaces_list:
    #    yaml_tree = ast.inline_subworkflow(yaml_tree, tools_cwl, namespaces)

    rootgraph = graphviz.Digraph(name=yaml_path)
    rootgraph.attr(newrank='True') # See graphviz layout comment above.
    rootgraph.attr(bgcolor="transparent") # Useful for making slides
    rootgraph.attr(fontcolor=font_edge_color)
    #rootgraph.attr(rankdir='LR') # When --graph_inline_depth 1, this usually looks better.
    with rootgraph.subgraph(name=f'cluster_{yaml_path}') as subgraph_gv:
        # get the label (if any) from the workflow
        step_i_wic_graphviz = yaml_tree.yml.get('wic', {}).get('graphviz', {})
        label = step_i_wic_graphviz.get('label', yaml_path)
        subgraph_gv.attr(label=label)
        subgraph_gv.attr(color='lightblue')  # color of cluster subgraph outline
        subgraph_nx = nx.DiGraph()
        graphdata = GraphData(yaml_path)
        subgraph = GraphReps(subgraph_gv, subgraph_nx, graphdata)
        compiler_info = compiler.compile_workflow(yaml_tree, args, [], [subgraph], {}, {}, tools_cwl, True, relative_run_path=True)
        rose_tree = compiler_info.rose

    utils.write_to_disk(rose_tree, Path('autogenerated/'), relative_run_path=True)

    if args.cwl_run_slurm:
        labshare.upload_all(rose_tree, tools_cwl, args, True)

    # Render the GraphViz diagram
    rootgraph.render(format='png') # Default pdf. See https://graphviz.org/docs/outputs/
    #rootgraph.view() # viewing does not work on headless machines (and requires xdg-utils)
    
    if args.cwl_run_local:
        # Stage input files to autogenerated/ (if any).
        cmd = ['cp', f'{Path(args.yaml).parent}/*', 'autogenerated/']
        print('Running ' + ' '.join(cmd))
        proc = sub.run(' '.join(cmd), shell=True)
        proc.check_returncode()

        yaml_stem = Path(args.yaml).stem
        yaml_stem = yaml_stem + '_inline' if args.cwl_inline_subworkflows else yaml_stem
        cmd = ['cwltool', '--parallel', '--cachedir', args.cachedir, '--outdir', 'outdir', f'autogenerated/{yaml_stem}.cwl', f'autogenerated/{yaml_stem}_inputs.yml']
        print('Running ' + ' '.join(cmd))
        sub.run(cmd)


if __name__ == '__main__':
    main()