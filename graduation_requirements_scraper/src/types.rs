use serde::Serialize;

/// Represents a set of requirements which do not all
/// need to be met
#[derive(Serialize, Debug)]
struct SomeOf {
    /// Minimum number of requirements which must be met
    min_number: Option<usize>,

    /// Maximum number of requirements which can be met
    max_number: Option<usize>,

    /// Set of requirements
    items: Vec<GraduationReq>,
}

/// Represents a given regex match for a course.
#[derive(Serialize, Debug)]
struct RegexMatch {
    /// Key of course to check
    key: String,

    /// Regex to validate against the key
    regex: String,
}

#[derive(Serialize, Debug)]
#[serde(tag = "type", rename_all = "snake_case")]
enum GraduationReq {
    /// Represents a set of requirements
    /// which must be met together
    Group {
        /// Name of this requirement
        name: Option<String>,

        /// Set of requirements which must all be filled
        all: Vec<GraduationReq>,

        /// Set of requirements which only need a certain
        /// number to be filled
        some: SomeOf,

        /// Should courses be allowed to count towards
        /// multiple requirements in this group?
        allow_overlap: bool,
    },

    /// Represents that courses in a certain range must
    /// meet given requirements
    NumericRestriction {
        /// Name of this requirement
        name: Option<String>,

        /// Minimum number of credits which must meet these
        /// requirements
        min_number_credits: Option<usize>,

        /// Maximum number of credits which can meet these
        /// requirements
        max_number_credits: Option<usize>,

        /// Requirement which these credits must meet
        value: Box<GraduationReq>,
    },

    /// Represents a set of regexes which must be met
    Regex {
        /// Name of this requirement
        name: Option<String>,

        /// Regexes to validate
        matches: Vec<RegexMatch>,
    },

    /// Checks if a course has a boolean property assigned
    Property {
        /// Name of this requirement
        name: Option<String>,

        /// Name of property to check
        property: String,

        /// Is this requirement met if the property exists?
        /// `false` means that this requirement is for the property
        /// to _not_ exist.
        applies_if_assigned: bool,
    },

    /// Represents a specific course which must be taken
    Course {
        /// Name of this requirement
        name: Option<String>,

        /// Four letter department code for this course
        dept: String,

        /// Course number (e.g. 2600)
        coid: usize,
    },
}
