- allow the 'key' columns to be more than just 'model' and 'scenario' so that `OpenSCMDataFrame` could have 'model-iam', 'model-climate' and 'scenario' as its 'key' columns rather than relying on the fragile convention that 'scenario' in `OpenSCMDataFrame` is the underscore-separated combination of `IamDataFrame`'s model and scenario



to, join model scenario, make model column equal to unset
from, split scenario column, put model column into variable name
