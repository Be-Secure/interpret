# Copyright (c) 2023 The InterpretML Contributors
# Distributed under the MIT software license

import logging

import dash
import dash.development.base_component as dash_base

# NOTE: Even though this isn't used here, it has to be imported to work.
import dash_cytoscape as cyto  # noqa: F401
from dash import dash_table as dt
from dash import dcc, html
from dash.dependencies import Input, Output
from pandas.core.generic import NDFrame
from plotly import graph_objs as go

_log = logging.getLogger(__name__)


# Constants
MAX_NUM_PANES = 5


class UDash(dash.Dash):
    def __init__(self, *args, **kwargs):
        self.ctx = kwargs.pop("ctx", None)
        self.ctx_item = kwargs.pop("ctx_item", None)
        self.options = kwargs.pop("options", None)
        super().__init__(*args, **kwargs)


DATA_TABLE_DEFAULTS = {
    "fixed_rows": {"headers": True, "data": 0},
    "filter_action": "native",
    "sort_action": "native",
    "virtualization": True,
    "editable": False,
    "style_table": {"height": "250px", "overflowX": "auto", "overflowY": "auto"},
    "css": [
        {
            "selector": ".dash-cell div.dash-cell-value",
            "rule": "display: inline; white-space: inherit; overflow: inherit;",
        },
        {"selector": ".dash-spreadsheet-container .sort", "rule": "float: left;"},
        {
            "selector": ".dash-select-cell input[type=checkbox]",
            "rule": "transform: scale(1.5);",
        },
    ],
    "style_cell": {
        "textAlign": "right",
        "paddingTop": "5px",
        "paddingBottom": "5px",
        "paddingLeft": "5px",
        "paddingRight": "7.5px",
        "fontFamily": '"Open Sans", "HelveticaNeue", "Helvetica Neue", Helvetica, Arial, sans-serif',
        "whiteSpace": "no-wrap",
        "overflow": "hidden",
        "maxWidth": 0,
    },
    "style_data": [{"backgroundColor": "white"}],
    "style_data_conditional": [
        {"if": {"row_index": "odd"}, "backgroundColor": "#f9f9f9"}
    ],
    "style_header": {
        "fontWeight": "bold",
        # 'fontSize': '1.25em',
        "backgroundColor": "#eaeaea",
        # 'color': 'white'
    },
}


# Dash app for a single explanation only
def generate_app_mini(
    ctx_item,
    url_base_pathname=None,
    requests_pathname_prefix=None,
    routes_pathname_prefix=None,
):
    """Generates the mini Dash application including callbacks..

    Returns:
        The dash app itself.
    """
    _log.info("Generating mini dash")

    # Initialize
    app = UDash(
        __name__,
        url_base_pathname=url_base_pathname,
        requests_pathname_prefix=requests_pathname_prefix,
        routes_pathname_prefix=routes_pathname_prefix,
    )
    app.scripts.config.serve_locally = True
    app.css.config.serve_locally = True
    app.config["suppress_callback_exceptions"] = True
    app.ctx_item = ctx_item
    app.logger.handlers = []
    app.title = "InterpretML"
    server = app.server

    # Items in drop-down.
    explanation, selector = ctx_item
    data_options = [{"label": "Summary", "value": -1}]
    options_list = []

    has_selector = selector is not None

    select_css = ""
    if has_selector:
        for i in range(len(selector)):
            col_strs = []
            for col_idx in range(min(3, len(selector.columns))):
                col_strs.append(
                    f"{selector.columns[col_idx]} ({selector.iloc[i, col_idx]})"
                )

            label_str = " | ".join(col_strs)
            label_str = f"{i} : {label_str}"
            options_list.append({"label": label_str, "value": i})
        data_options.extend(options_list)
    else:
        select_css = "hdn"

    # Define selector component
    selector_component = html.Div(
        [
            html.Div(
                [
                    html.Div(
                        html.Div("Select Component to Graph", className="card-title"),
                        className="card-header",
                    ),
                    html.Div(
                        [
                            dcc.Dropdown(
                                id="component-drop",
                                options=data_options,
                                multi=False,
                                value=-1,
                            )
                        ],
                        className="card-body",
                    ),
                ],
                className="card",
            )
        ],
        className=select_css,
    )

    # Define viz component
    viz_component = html.Div(id="viz-container")

    # Define layout
    app.layout = html.Div(
        [
            html.Div([selector_component, viz_component]),
            # NOTE: Workaround for tables not rendering
            # TODO: Check if this is needed with the new tables.
            html.Div(dt.DataTable(data=[{}]), style={"display": "none"}),
        ],
        className="mini-app",
    )

    @app.callback(
        Output("viz-container", "children"), [Input("component-drop", "value")]
    )
    def update_viz_container(value):
        if value is None:
            return None

        explanation, selector = app.ctx_item
        if value == -1:
            output_div = gen_overall_plot(explanation, int(value))
        else:
            output_div = gen_plot(explanation, int(value), 0, 0)

        return output_div

    @server.errorhandler(Exception)
    def handle_error(e):  # pragma: no cover
        _log.error(e, exc_info=True)
        return "Internal Server Error caught by udash. See logs if available.", 500

    _log.info("Generated mini dash")
    return app


def gen_overall_plot(exp, model_idx):
    figure = exp.visualize(key=None)
    if figure is None:
        _log.info(f"No overall plot to display: {model_idx}|{exp.name}")
        # Provide default 'no overall' graph
        figure = r"""
                <style>
                .center {
                    position: absolute;
                    left: 50%;
                    top: 50%;
                    -webkit-transform: translate(-50%, -50%);
                    transform: translate(-50%, -50%);
                }
                </style>
                <div class='center'><h1>No Overall Graph</h1></div>
            """

    # NOTE: We also have support for data frames, but we don't advertise it.
    if isinstance(figure, NDFrame):
        records = figure.to_dict("records")
        columns = [
            {"name": col, "id": col}
            for _, col in enumerate(figure.columns)
            if col != "id"
        ]
        output_graph = html.Div(
            [
                dt.DataTable(
                    data=records,
                    columns=columns,
                    filter_action="naive",
                    sort_action="naive",
                    editable=False,
                    id=f"overall-graph-{model_idx}",
                )
            ]
        )
    elif isinstance(figure, str):
        output_graph = html.Div(
            [
                html.Iframe(
                    id=f"overall-graph-{model_idx}",
                    sandbox="",
                    srcDoc=figure,
                    style={"border": "0", "width": "100%", "height": "390px"},
                )
            ]
        )
    elif isinstance(figure, go.Figure):
        output_graph = dcc.Graph(
            id=f"overall-graph-{model_idx}",
            figure=figure,
            config={"displayModeBar": "hover"},
        )
    elif isinstance(figure, dash_base.Component):
        output_graph = figure
        output_graph.id = f"overall-graph-{model_idx}"
    else:  # pragma: no cover
        _type = type(figure)
        _log.warning(f"Visualization type not supported: {_type}")
        msg = f"Not supported visualization type: {_type}"
        raise Exception(msg)

    name = exp.name
    return html.Div(
        [
            html.Div(
                html.Div(f"{name} (Overall)", className="card-title"),
                className="card-header",
            ),
            html.Div(output_graph, className="card-body card-figure"),
        ],
        className="card",
    )


def gen_plot(exp, picker, model_idx, counter):
    figure = exp.visualize(key=picker)
    if isinstance(figure, NDFrame):
        records = figure.to_dict("records")
        columns = [
            {"name": col, "id": col}
            for _, col in enumerate(figure.columns)
            if col != "id"
        ]
        output_graph = dt.DataTable(
            data=records,
            columns=columns,
            id=f"graph-{model_idx}-{counter}",
            **DATA_TABLE_DEFAULTS,
        )
    elif isinstance(figure, str):
        output_graph = html.Div(
            [
                html.Iframe(
                    id=f"graph-{model_idx}-{counter}",
                    sandbox="",
                    srcDoc=figure,
                    style={"border": "0", "width": "100%", "height": "390px"},
                )
            ]
        )
    elif isinstance(figure, go.Figure):
        output_graph = dcc.Graph(
            id=f"graph-{model_idx}-{counter}",
            figure=figure,
            config={"displayModeBar": "hover"},
        )
    elif isinstance(figure, dash_base.Component):
        output_graph = figure
        output_graph.id = f"graph-{model_idx}-{counter}"
    else:  # pragma: no cover
        _type = type(figure)
        _log.warning(f"Visualization type not supported: {_type}")
        msg = f"Not supported visualization type: {_type}"
        raise Exception(msg)

    idx_str = str(picker)
    name = exp.name
    return html.Div(
        [
            html.Div(
                html.Div(f"{name} [{idx_str}]", className="card-title"),
                className="card-header",
            ),
            html.Div(output_graph, className="card-body card-figure"),
        ],
        className="card",
    )


# Dash app code
# TODO: Consider reducing complexity of this function.
def generate_app_full(
    url_base_pathname=None, requests_pathname_prefix=None, routes_pathname_prefix=None
):
    """Generates the Dash application including callbacks.

    Returns:
        The dash app itself.
    """

    _log.info("Generating full dash")

    # Initialize
    app = UDash(
        __name__,
        url_base_pathname=url_base_pathname,
        requests_pathname_prefix=requests_pathname_prefix,
        routes_pathname_prefix=routes_pathname_prefix,
    )
    app.scripts.config.serve_locally = True
    app.css.config.serve_locally = True
    app.config["suppress_callback_exceptions"] = True
    app.logger.handlers = []
    app.title = "InterpretML"
    server = app.server

    # Define layout
    app.layout = html.Div(
        [
            html.Div([html.H2("Interpret ML Dashboard")], className="banner"),
            html.Div(
                dcc.Tabs(
                    id="tabs",
                    children=[
                        dcc.Tab(
                            label="Overview",
                            value="overview",
                            children=html.Div(id="overview-tab", className="contain"),
                        ),
                        dcc.Tab(
                            label="Data",
                            value="data",
                            children=html.Div(id="data-tab", className="contain"),
                        ),
                        dcc.Tab(
                            label="Performance",
                            value="perf",
                            children=html.Div(id="perf-tab", className="contain"),
                        ),
                        dcc.Tab(
                            label="Global",
                            value="global",
                            children=html.Div(id="global-tab", className="contain"),
                        ),
                        dcc.Tab(
                            label="Local",
                            value="local",
                            children=html.Div(id="local-tab", className="contain"),
                        ),
                    ],
                    vertical=False,
                    mobile_breakpoint=480,
                    value="overview",
                )
            ),
            # NOTE: Workaround for tables not rendering
            html.Div(dt.DataTable(data=[{}]), style={"display": "none"}),
        ],
        className="app",
    )

    def get_model_records(ctx):
        """Extracts model records passed to Dash.

        Args:
            ctx: List of explanations.

        Returns:
            List of dictionaries denoting name and type of explanations.
        """
        _types = {
            "data": "Data",
            "perf": "Performance",
            "global": "Global",
            "local": "Local",
        }
        return [
            {
                # 'Index': i,
                "Name": ctx[i][0].name,
                "Type": _types[ctx[i][0].explanation_type],
            }
            for i in range(len(ctx))
        ]

    def gen_overview_tab():
        """Generates overview tab.

        Returns:
            Dash component that handles overview tab entire.
        """

        # Define components
        ctx = app.ctx
        records = get_model_records(ctx)
        columns = [{"name": "Name", "id": "Name"}, {"name": "Type", "id": "Type"}]
        table = dt.DataTable(
            data=records, columns=columns, row_selectable=False, **DATA_TABLE_DEFAULTS
        )
        markdown = """
Welcome to Interpret ML's dashboard. Here you will find en-masse visualizations for your machine learning pipeline.

***

The explanations available are split into tabs, each covering an aspect of the pipeline.
- **Data** covers exploratory data analysis, designed mostly for feature-level.
- **Performance** covers model performance both overall and user-defined groups.
- **Global** explains model decisions overall.
- **Local** explains a model decision for every instance/observation.
"""

        # Wrap as cards.
        cards = []
        cards.append(
            html.Div(
                [
                    html.Div(
                        html.Div("Introduction", className="card-title"),
                        className="card-header",
                    ),
                    html.Div(dcc.Markdown(markdown), className="card-body"),
                ],
                className="card",
            )
        )
        cards.append(
            html.Div(
                [
                    html.Div(
                        html.Div("Available Explanations", className="card-title"),
                        className="card-header",
                    ),
                    html.Div(html.Div(table), className="card-body"),
                ],
                className="card",
            )
        )

        return html.Div(cards)

    def gen_tab(explanation_type):
        _log.debug(f"Generating tab: {explanation_type}")
        ctx = app.ctx
        options = app.options
        data_options = [
            {"label": ctx[i][0].name, "value": i}
            for i in range(len(ctx))
            if ctx[i][0].explanation_type == explanation_type
        ]
        indices = html.Div(
            [
                html.Div(
                    id=f"{explanation_type}-instance-idx-{i!s}",
                    className="hdn",
                )
                for i in range(MAX_NUM_PANES)
            ]
        )
        specific_indices = html.Div(
            [
                html.Div(
                    id=f"{explanation_type}-specific-idx-{i!s}",
                    className="hdn",
                )
                for i in range(MAX_NUM_PANES)
            ]
        )
        shared_indices = html.Div(
            [html.Div(id=f"{explanation_type}-shared-idx", className="hdn")]
        )

        # NOTE: Don't question this. It was written in blood.
        shared_value = options["share_tables"].get(explanation_type, False)
        shared_value = "True" if shared_value is True else None
        is_shared = html.Div(
            id=f"{explanation_type}-is-shared",
            children=shared_value,
            className="hdn",
        )
        _log.debug(f"Tab {explanation_type} is_shared: {shared_value}")
        return html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            html.Div("Select Explanation", className="card-title"),
                            className="card-header",
                        ),
                        html.Div(
                            [
                                dcc.Dropdown(
                                    id=f"{explanation_type}-model-drop",
                                    options=data_options,
                                    multi=True,
                                )
                            ],
                            className="card-body",
                        ),
                    ],
                    className="card",
                ),
                is_shared,
                indices,
                shared_indices,
                specific_indices,
                html.Div(id=f"{explanation_type}-shared-table-container"),
                html.Div(id=f"{explanation_type}-tabs-container"),
            ]
        )

    # Callback generators

    def register_pane_cb(explanation_type):
        def output_callback(value, is_shared):
            _log.debug(f"Registering pane: {explanation_type}|{value}|{is_shared}")
            if value is None:
                return None

            ctx = app.ctx
            components = []

            for i, model_idx in enumerate(value):
                s_i = str(i)

                df = ctx[model_idx][1]
                if df is not None:
                    records = df.to_dict("records")
                    if is_shared is not None:
                        component = html.Div()
                    else:
                        columns = [
                            {"name": col, "id": col}
                            for _, col in enumerate(df.columns)
                            if col != "id"
                        ]
                        instance_table = dt.DataTable(
                            data=records,
                            columns=columns,
                            id=f"{explanation_type}-instance-table-{s_i}",
                            row_selectable="multi",
                            **DATA_TABLE_DEFAULTS,
                        )
                        component = html.Div(
                            [
                                html.Div(
                                    html.Div(
                                        "Select Instances", className="card-title"
                                    ),
                                    className="card-header",
                                ),
                                html.Div(
                                    [html.Div([instance_table])],
                                    className="card-body card-table",
                                ),
                            ],
                            className="card",
                        )

                    components.append(
                        html.Div(
                            [
                                component,
                                html.Div(
                                    id=f"{explanation_type}-plots-container-{s_i}"
                                ),
                                html.Div(
                                    id=f"{explanation_type}-overall-plot-container-{s_i}"
                                ),
                            ],
                            className="gr-col",
                        )
                    )
                else:
                    _log.info(f"No df provided in pane cb for model idx: {model_idx}")
                    components.append(
                        html.Div(
                            [
                                html.Div(
                                    id=f"{explanation_type}-overall-plot-container-{s_i}"
                                )
                            ],
                            className="gr-col",
                        )
                    )
            return html.Div(components, className="gr")

        return output_callback

    def register_update_share_table_cb(explanation_type):
        def output_callback(value, is_shared):
            if is_shared is None:
                return None

            if value is None or len(value) == 0:
                return None
            return gen_share_table_container(value, explanation_type)

        return output_callback

    def register_update_idx_cb():
        def output_callback(data, derived_virtual_selected_row_ids):
            if derived_virtual_selected_row_ids is None:
                return None
            return [data[i]["id"] for i in derived_virtual_selected_row_ids]

        return output_callback

    def register_update_instance_idx_cb():
        def output_callback(is_shared, shared_indices, specific_indices):
            if is_shared is not None:
                return shared_indices
            return specific_indices

        return output_callback

    def register_update_plots_cb(pane_idx):
        def output_callback(model_idx, instance_idx):
            if pane_idx >= len(model_idx):  # pragma: no cover
                _log.warning(
                    f"Pane index {pane_idx} larger than selected explanations."
                )
                return None
            _log.debug(f"Updating plots: {pane_idx}|{model_idx}|{instance_idx}")
            return gen_plots_container(model_idx[pane_idx], instance_idx)

        return output_callback

    def register_update_overall_plot_cb(pane_idx):
        def output_callback(model_idx, empty):
            if pane_idx >= len(model_idx):  # pragma: no cover
                _log.warning(
                    f"Pane index {pane_idx} larger than selected explanations."
                )
                return None
            _log.debug(f"Updating overall plots: {model_idx}")
            return gen_overall_plot_container(model_idx[pane_idx])

        return output_callback

    # DYNAMIC
    tab_list = ["data", "perf", "global", "local"]
    for tab in tab_list:
        app.callback(
            Output(f"{tab}-tabs-container", "children"),
            [
                Input(f"{tab}-model-drop", "value"),
                Input(f"{tab}-is-shared", "children"),
            ],
        )(register_pane_cb(tab))

        for i in range(MAX_NUM_PANES):
            s_i = str(i)
            app.callback(
                Output(f"{tab}-plots-container-{s_i}", "children"),
                [
                    Input(f"{tab}-model-drop", "value"),
                    Input(f"{tab}-instance-idx-{s_i}", "children"),
                ],
            )(register_update_plots_cb(i))
            app.callback(
                Output(f"{tab}-overall-plot-container-{s_i}", "children"),
                [
                    Input(f"{tab}-model-drop", "value"),
                    # NOTE: Fixes concurrency bug for panes. Find better solution.
                    Input(f"{tab}-instance-idx-{s_i}", "children"),
                ],
            )(register_update_overall_plot_cb(i))

        app.callback(
            Output(f"{tab}-shared-table-container", "children"),
            [
                Input(f"{tab}-model-drop", "value"),
                Input(f"{tab}-is-shared", "children"),
            ],
        )(register_update_share_table_cb(tab))

        app.callback(
            Output(f"{tab}-shared-idx", "children"),
            [
                Input(f"{tab}-shared-table", "data"),
                Input(f"{tab}-shared-table", "derived_virtual_selected_row_ids"),
            ],
        )(register_update_idx_cb())
        for i in range(MAX_NUM_PANES):
            s_i = str(i)
            app.callback(
                Output(f"{tab}-instance-idx-{s_i}", "children"),
                [
                    Input(f"{tab}-is-shared", "children"),
                    Input(f"{tab}-shared-idx", "children"),
                    Input(f"{tab}-specific-idx-{s_i}", "children"),
                ],
            )(register_update_instance_idx_cb())
            app.callback(
                Output(f"{tab}-specific-idx-{s_i}", "children"),
                [
                    Input(f"{tab}-instance-table-{s_i}", "data"),
                    Input(
                        f"{tab}-instance-table-{s_i}",
                        "derived_virtual_selected_row_ids",
                    ),
                ],
            )(register_update_idx_cb())

    def gen_share_table_container(model_idxs, explanation_type):
        _log.debug(
            f"Generating shared table container: {model_idxs}|{explanation_type}"
        )

        # Since tables are shared (identical in content), we take the first.
        model_idx = model_idxs[0]
        ctx = app.ctx
        df = ctx[model_idx][1]
        if df is not None:
            records = df.to_dict("records")
            columns = [
                {"name": col, "id": col}
                for _, col in enumerate(df.columns)
                if col != "id"
            ]
            instance_table = dt.DataTable(
                data=records,
                columns=columns,
                id=f"{explanation_type}-shared-table",
                row_selectable="multi",
                **DATA_TABLE_DEFAULTS,
            )
            return html.Div(
                [
                    html.Div(
                        html.Div("Select Components to Graph", className="card-title"),
                        className="card-header",
                    ),
                    html.Div(
                        [html.Div([instance_table])], className="card-body card-table"
                    ),
                ],
                className="card",
            )
        return None

    def gen_plots_container(model_idx, picker_idx):
        if model_idx is None or not picker_idx:
            return None

        _log.debug(f"Generating plots: {model_idx}|{picker_idx}")

        ctx = app.ctx
        exp = ctx[model_idx][0]

        output = []
        counter = 0
        for picker in reversed(picker_idx):
            output_div = gen_plot(exp, picker, model_idx, counter)
            counter += 1
            output.append(output_div)
        return html.Div(output)

    def gen_overall_plot_container(model_idx):
        _log.debug(f"Generating overall plots: {model_idx}")

        ctx = app.ctx
        exp = ctx[model_idx][0]

        output_div = gen_overall_plot(exp, model_idx)

        return html.Div(output_div)

    @server.errorhandler(Exception)
    def handle_error(e):  # pragma: no cover
        _log.error(e, exc_info=True)
        return "Internal Server Error caught by udash. See logs if available.", 500

    @app.callback(Output("data-tab", "children"), [Input("tabs", "value")])
    def update_data_tab_content(tab):
        if tab is None or tab != "data":
            return None
        return gen_tab(tab)

    @app.callback(Output("perf-tab", "children"), [Input("tabs", "value")])
    def update_perf_tab_content(tab):
        if tab is None or tab != "perf":
            return None
        return gen_tab(tab)

    @app.callback(Output("overview-tab", "children"), [Input("tabs", "value")])
    def update_overview_tab_content(tab):
        if tab is None or tab != "overview":
            return None
        return gen_overview_tab()

    @app.callback(Output("local-tab", "children"), [Input("tabs", "value")])
    def update_local_tab_content(tab):
        if tab is None or tab != "local":
            return None
        return gen_tab(tab)

    @app.callback(Output("global-tab", "children"), [Input("tabs", "value")])
    def update_global_tab_content(tab):
        if tab is None or tab != "global":
            return None
        return gen_tab(tab)

    _log.info("Generated full dash")
    return app


def _expand_ctx_item(item):
    if isinstance(item, tuple):
        explanation = item[0]
        selector = item[1]
    else:
        explanation = item
        selector = explanation.selector

    if selector is not None:
        df = selector.copy()
        df = df.reset_index(drop=True)
        df["id"] = df.index
        df *= 1
    else:
        df = None

    return (explanation, df)


def generate_app(
    ctx,
    options,
    url_base_pathname=None,
    requests_pathname_prefix=None,
    routes_pathname_prefix=None,
):
    # If we are passed a single explanation as a scalar, generate mini app.
    if not isinstance(ctx, list):
        new_item = _expand_ctx_item(ctx)
        return generate_app_mini(
            new_item,
            url_base_pathname=url_base_pathname,
            requests_pathname_prefix=requests_pathname_prefix,
            routes_pathname_prefix=routes_pathname_prefix,
        )

    app = generate_app_full(
        requests_pathname_prefix=requests_pathname_prefix,
        routes_pathname_prefix=routes_pathname_prefix,
    )
    new_ctx = []
    # Provide indexes for selecting in dashboard. This is required.

    for item in ctx:
        new_item = _expand_ctx_item(item)
        new_ctx.append(new_item)

    # Determine if we share tables for each explanation type.
    new_options = options.copy()
    share_tables = new_options["share_tables"]
    supported_types = ["data", "perf", "global", "local"]
    _log.debug(f"PRE shared_tables: {share_tables}")
    if share_tables is None:
        # TODO: Revisit when we support custom tabs from users.
        shared_frames = {supported_type: True for supported_type in supported_types}
        first_dfs = {}
        for expl, df in new_ctx:
            expl_type = expl.explanation_type
            if first_dfs.get(expl_type) is None:
                first_dfs[expl_type] = df

            if df is None or not df.equals(first_dfs[expl_type]):
                shared_frames[expl_type] = False
    elif share_tables is True:
        shared_frames = {supported_type: True for supported_type in supported_types}
    elif share_tables is False:
        shared_frames = {supported_type: False for supported_type in supported_types}
    elif isinstance(share_tables, dict):
        shared_frames = share_tables
    else:  # pragma: no cover
        msg = "share_tables option must be True|False|None or dict."
        raise Exception(msg)

    new_options["share_tables"] = shared_frames
    _log.debug(f"POST shared_tables: {shared_frames}")

    app.ctx = new_ctx
    app.options = new_options
    return app
