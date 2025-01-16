import sys
from pathlib import Path
import shutil
import subprocess as sub
import traceback
from typing import Dict

import graphviz
import networkx as nx
import yaml

from sophios.utils_yaml import wic_loader
from . import input_output as io
from . import post_compile as pc
from . import ast, cli, compiler, inference, inlineing, plugins, run_local, utils  # , utils_graphs
from .schemas import wic_schema
from .wic_types import GraphData, GraphReps, Json, StepId, Yaml, YamlTree


def main() -> None:
    """See docs/userguide.md"""
    args = cli.parser.parse_args()
    plugins.logging_filters()

    # User may specify a different homedir
    default_config_file = Path(args.homedir)/'wic'/'global_config.json'
    if args.generate_config:
        if default_config_file.exists():
            print(f'Config already exists. To overwrite delete {default_config_file.parent} directory. Exiting')
        else:
            basic_config = io.get_basic_config()
            io.write_config_to_disk(basic_config, default_config_file)
            io.move_adapters_and_examples(basic_config)
            print('Finished generating config. Exiting.')
        sys.exit(0)
    global_config: Json = io.get_config(Path(args.config_file), default_config_file)

    tools_cwl = plugins.get_tools_cwl(global_config,
                                      args.validate_plugins,
                                      not args.no_skip_dollar_schemas,
                                      args.quiet)
    # This takes ~1 second but it is not really necessary.
    # utils_graphs.make_plugins_dag(tools_cwl, args.graph_dark_theme)
    # pass around config object instead of reading from the disk!
    yml_paths = plugins.get_yml_paths(global_config)

    # Perform initialization via mutating global variables (This is not ideal)
    compiler.inference_rules = global_config.get('inference_rules', {})
    inference.renaming_conventions = global_config.get('renaming_conventions', [])

    # Generate schemas for validation and vscode IntelliSense code completion
    yaml_stems = utils.flatten([list(p) for p in yml_paths.values()])
    schema_store: Dict[str, Json] = {}
    validator = wic_schema.get_validator(tools_cwl, yaml_stems, schema_store, write_to_disk=False)

    # Generating yml schemas every time takes ~20 seconds and guarantees the
    # subworkflow schemas are always up to date. However, since it compiles all
    # yml files, if there are any errors in any of the yml files, the user may
    # be confused by an error message when the --yaml file is correct.
    # For now, require the user to update the schemas manually. In the future,
    # we may use a filewatcher.
    if args.generate_schemas:
        yml_paths_tuples = [(yml_path_str, yml_path)
                            for yml_namespace, yml_paths_dict in yml_paths.items()
                            for yml_path_str, yml_path in yml_paths_dict.items()]

        for yml_path_str, yml_path in yml_paths_tuples:
            schema = wic_schema.compile_workflow_generate_schema(args.homedir, yml_path_str, yml_path,
                                                                 tools_cwl, yml_paths, validator,
                                                                 args.ignore_validation_errors,
                                                                 args.allow_raw_cwl)
            # overwrite placeholders in schema_store. See comment in get_validator()
            schema_store[schema['$id']] = schema

        # Now that we compiled all of the subworkflows once with the permissive/weak schema,
        # compile the root yml workflow again with the restrictive/strict schema.
        validator = wic_schema.get_validator(tools_cwl, yaml_stems, schema_store, write_to_disk=True)

    if args.generate_schemas:
        print('Finished generating schemas. Exiting.')
        sys.exit(0)

    yaml_path = args.yaml
    yaml_stem = Path(args.yaml).stem

    # Load the high-level yaml root workflow file.
    with open(yaml_path, mode='r', encoding='utf-8') as y:
        root_yaml_tree: Yaml = yaml.load(y.read(), Loader=wic_loader())
    Path('autogenerated/').mkdir(parents=True, exist_ok=True)
    wic = {'wic': root_yaml_tree.get('wic', {})}
    plugin_ns = wic['wic'].get('namespace', 'global')
    step_id = StepId(yaml_path, plugin_ns)
    y_t = YamlTree(step_id, root_yaml_tree)
    yaml_tree_raw = ast.read_ast_from_disk(args.homedir, y_t, yml_paths, tools_cwl, validator,
                                           args.ignore_validation_errors)
    # Write the combined workflow (with all subworkflows as children) to disk.
    # NOTE: This is completely optional and for debugging purposes only.
    with open(f'autogenerated/{Path(yaml_path).stem}_tree_raw.wic', mode='w', encoding='utf-8') as f:
        f.write(yaml.dump(yaml_tree_raw.yml))
    yaml_tree = ast.merge_yml_trees(yaml_tree_raw, {}, tools_cwl)
    with open(f'autogenerated/{Path(yaml_path).stem}_tree_merged.wic', mode='w', encoding='utf-8') as f:
        f.write(yaml.dump(yaml_tree.yml))
    root_yml_dir_abs = Path(args.yaml).parent.absolute()
    yaml_tree = ast.python_script_generate_cwl(yaml_tree, root_yml_dir_abs, tools_cwl)
    with open(f'autogenerated/{Path(yaml_path).stem}_tree_python_script.wic', mode='w', encoding='utf-8') as f:
        f.write(yaml.dump(yaml_tree.yml))

    if args.cwl_inline_subworkflows:
        while True:
            # Inlineing changes the namespaces, so we have to get new namespaces after each inlineing operation.
            namespaces_list = inlineing.get_inlineable_subworkflows(yaml_tree, tools_cwl, False, [])
            if namespaces_list == []:
                break

            # print('inlineing', namespaces_list[0])
            yaml_tree, _len_substeps = inlineing.inline_subworkflow(yaml_tree, namespaces_list[0])

        # Append _inline here instead of in io.write_to_disk()
        step_id = StepId(yaml_tree.step_id.stem + '_inline', yaml_tree.step_id.plugin_ns)
        yaml_tree = YamlTree(step_id, yaml_tree.yml)

        with open(f'autogenerated/{Path(yaml_path).stem}_tree_merged_inlined.wic', mode='w', encoding='utf-8') as f:
            f.write(yaml.dump(yaml_tree.yml))

    rootgraph = graphviz.Digraph(name=yaml_path)
    rootgraph.attr(newrank='True')  # See graphviz layout comment above.
    rootgraph.attr(bgcolor="transparent")  # Useful for making slides
    font_edge_color = 'black' if args.graph_dark_theme else 'white'
    rootgraph.attr(fontcolor=font_edge_color)

    # This can be used to visually 'inline' all subworkflows (but NOT the CWL).
    # rootgraph.attr(style='invis')
    # Note that since invisible objects still affect the graphviz layout (by design),
    # this can be used to control the layout of the individual nodes, even if
    # you don't necessarily want subworkflows.

    # rootgraph.attr(rankdir='LR') # When --graph_inline_depth 1, this usually looks better.
    with rootgraph.subgraph(name=f'cluster_{yaml_path}') as subgraph_gv:
        # get the label (if any) from the workflow
        step_i_wic_graphviz = yaml_tree.yml.get('wic', {}).get('graphviz', {})
        label = step_i_wic_graphviz.get('label', yaml_path)
        subgraph_gv.attr(label=label)
        subgraph_gv.attr(color='lightblue')  # color of cluster subgraph outline
        subgraph_nx = nx.DiGraph()
        graphdata = GraphData(yaml_path)
        subgraph = GraphReps(subgraph_gv, subgraph_nx, graphdata)
        try:
            compiler_info = compiler.compile_workflow(yaml_tree, args, [], [subgraph], {}, {}, {}, {},
                                                      tools_cwl, True, relative_run_path=True, testing=False)
        except Exception as e:
            # Certain constraints are conditionally dependent on values and are
            # not easily encoded in the schema, so catch them here.
            # Moreover, although we check for the existence of input files in
            # stage_input_files, we cannot encode file existence in json schema
            # to check the python_script script: tag before compile time.
            print('Failed to compile', yaml_path)
            print(f'See error_{yaml_stem}.txt for detailed technical information.')
            # Do not display a nasty stack trace to the user; hide it in a file.
            with open(f'error_{yaml_stem}.txt', mode='w', encoding='utf-8') as f:
                # https://mypy.readthedocs.io/en/stable/common_issues.html#python-version-and-system-platform-checks
                if sys.version_info >= (3, 10):
                    traceback.print_exception(type(e), value=e, tb=None, file=f)
                else:
                    traceback.print_exception(etype=type(e), value=e, tb=None, file=f)
            sys.exit(1)
        rose_tree = compiler_info.rose
    rose_tree = plugins.cwl_prepend_dockerFile_include_path_rosetree(rose_tree)

    if args.partial_failure_enable:
        rose_tree = plugins.cwl_update_outputs_optional_rosetree(rose_tree)

    io.write_to_disk(rose_tree, Path('autogenerated/'), True, args.inputs_file)

    if args.cwl_inline_runtag:
        rose_tree = pc.cwl_inline_runtag(rose_tree)
    io.write_to_disk(rose_tree, Path('autogenerated/'), True, args.inputs_file)

    if args.graphviz:
        if shutil.which('dot'):
            # Render the GraphViz diagram
            rootgraph.save(f'autogenerated/{yaml_stem}.wic.gv')
            cmdline = f'cat autogenerated/{yaml_stem}.wic.gv | dot -Tpng > autogenerated/{yaml_stem}.wic.gv.png'
            sub.run(cmdline, shell=True, capture_output=False, check=False)
            # Use the explicit code above because the .render() method saves
            # the png file in the same directory as the original yaml_path
            # rootgraph.render(format='png')  # Default pdf. See https://graphviz.org/docs/outputs/

            # For comparison, the built-in cwltool graphiz support generates a visual abomination:
            cmdline = f'cwltool_filterlog --print-dot autogenerated/{yaml_stem}.cwl | dot -Tsvg > autogenerated/{yaml_stem}.svg'
            sub.run(cmdline, shell=True, capture_output=True, check=False)
        else:
            print("Warning: Cannot generate graphviz diagrams because the `dot` executable was not found.")
            print("(This may happen if you installed the graphviz python package")
            print("but not the graphviz system package.)")

    if args.run_local or args.generate_run_script:
        pc.cwl_docker_extract(args.container_engine, args.pull_dir, yaml_stem)
        if args.docker_remove_entrypoints:
            rose_tree = pc.remove_entrypoints(args.container_engine, rose_tree)
        io.write_to_disk(rose_tree, Path('autogenerated/'), True, args.inputs_file)
        pc.find_and_create_output_dirs(rose_tree)
        run_local.run_local(args, rose_tree, args.cachedir, args.cwl_runner, False)

        # Finally, since there is an output file copying bug in cwltool,
        # we need to copy the output files manually. See comment above.
        if args.copy_output_files:
            run_local.copy_output_files(yaml_stem)


if __name__ == '__main__':
    main()
