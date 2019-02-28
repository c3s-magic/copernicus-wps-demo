import logging
import os

from pywps import FORMATS, ComplexInput, ComplexOutput, Format, LiteralInput, LiteralOutput, Process
from pywps.inout.literaltypes import make_allowedvalues
from pywps.app.Common import Metadata
from pywps.response.status import WPS_STATUS

from copernicus import runner, util
from copernicus.processes.utils import default_outputs, model_experiment_ensemble

LOGGER = logging.getLogger("PYWPS")


class PreprocessExample(Process):
    def __init__(self):
        inputs = [
            *model_experiment_ensemble(
                models=['EC-EARTH'],
                experiments=['historical'],
                ensembles=['r1i1p1'],
                start_end_year=(1850, 2005),
                start_end_defaults=(1980, 1989)
            ),
            LiteralInput('extract_levels', 'Extraction levels',
                         abstract='Choose an extraction level for the preprocessor.',
                         data_type='float',
                         #allowed_values=make_allowedvalues([0.0, 110000.0]),
                         default=85000.0),
        ]
        outputs = [
            *default_outputs(),
            ComplexOutput('plot', 'Output plot',
                          abstract='Generated output plot of ESMValTool processing.',
                          as_reference=True,
                          supported_formats=[Format('image/png')]),
            ComplexOutput('data', 'Data',
                          abstract='Generated output data of ESMValTool processing.',
                          as_reference=True,
                          supported_formats=[FORMATS.NETCDF]),
             ComplexOutput('archive', 'Archive',
                          abstract='The complete output of the ESMValTool processing as an zip archive.',
                          as_reference=True,
                          supported_formats=[Format('application/zip')]),
        ]

        super(PreprocessExample, self).__init__(
            self._handler,
            identifier="preproc",
            title="Python Demo",
            version=runner.VERSION,
            abstract="Generates a plot for temperature using ESMValTool."
             " The default run uses the following CMIP5 data:"
             " project=CMIP5, experiment=historical, ensemble=r1i1p1, variable=ta, model=MPI-ESM-LR, time_frequency=mon",  # noqa
            metadata=[
                Metadata('ESMValTool', 'http://www.esmvaltool.org/'),
                Metadata('Documentation',
                         'https://copernicus-wps-demo.readthedocs.io/en/latest/processes.html#pydemo',
                         role=util.WPS_ROLE_DOC),
                Metadata('Media',
                         util.diagdata_url() + '/pydemo/pydemo_thumbnail.png',
                         role=util.WPS_ROLE_MEDIA),
                Metadata('ESGF Testdata',
                         'https://esgf1.dkrz.de/thredds/catalog/esgcet/7/cmip5.output1.MPI-M.MPI-ESM-LR.historical.mon.atmos.Amon.r1i1p1.v20120315.html?dataset=cmip5.output1.MPI-M.MPI-ESM-LR.historical.mon.atmos.Amon.r1i1p1.v20120315.ta_Amon_MPI-ESM-LR_historical_r1i1p1_199001-199912.nc'),  # noqa
            ],
            inputs=inputs,
            outputs=outputs,
            status_supported=True,
            store_supported=True)

    def _handler(self, request, response):
        response.update_status("starting ...", 0)

        # build esgf search constraints
        constraints = dict(
            model1=request.inputs['model1'][0].data,
            ensemble1=request.inputs['ensemble1'][0].data,
            model2=request.inputs['model2'][0].data,
            ensemble2=request.inputs['ensemble2'][0].data,
            model3=request.inputs['model3'][0].data,
            ensemble3=request.inputs['ensemble3'][0].data,
            experiment=request.inputs['experiment'][0].data,
        )

        options = dict(
            extract_levels=request.inputs['extract_levels'][0].data
        )

        # generate recipe
        response.update_status("generate recipe ...", 10)
        recipe_file, config_file = runner.generate_recipe(
            workdir=self.workdir,
            diag='python',
            constraints=constraints,
            start_year=request.inputs['start_year'][0].data,
            end_year=request.inputs['end_year'][0].data,
            output_format='png',
            options=options
        )

        # recipe output
        response.outputs['recipe'].output_format = FORMATS.TEXT
        response.outputs['recipe'].file = recipe_file

        # run diag
        response.update_status("running diagnostic ...", 20)
        result = runner.run(recipe_file, config_file)
        logfile = result['logfile']
        work_dir = result['work_dir']
        plot_dir = result['plot_dir']

        response.outputs['success'].data = result['success']

        # log output
        response.outputs['log'].output_format = FORMATS.TEXT
        response.outputs['log'].file = logfile

        if not result['success']:
            LOGGER.exception('esmvaltool failed!')
            response.update_status("exception occured: " + result['exception'], 100)
            return response

        # result plot
        response.update_status("collecting output ...", 80)
        response.outputs['plot'].output_format = Format('application/png')
        response.outputs['plot'].file = runner.get_output(
            plot_dir,
            path_filter=os.path.join('diagnostic1', 'script1'),
            name_filter="CMIP5*",
            output_format="png")

        response.outputs['data'].output_format = FORMATS.NETCDF
        response.outputs['data'].file = runner.get_output(
            work_dir,
            path_filter=os.path.join('diagnostic1', 'script1'),
            name_filter="CMIP5*",
            output_format="nc")

        response.update_status("creating archive of diagnostic result ...", 90)

        response.outputs['archive'].output_format = Format('application/zip')
        response.outputs['archive'].file = runner.compress_output(os.path.join(self.workdir, 'output'), 'diagnostic_result.zip')

        response.update_status("done.", 100)
        return response